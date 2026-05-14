"""
SSRM Engine — orchestrates filtering, sorting, grouping, and pagination.
"""
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Dict, List, Optional

from django.db.models import QuerySet

from .fields import FieldDef
from .filters import apply_filters
from .grouping import handle_grouped_request
from .request import SSRMRequest
from .sorting import get_order_fields


@dataclass
class SSRMConfig:
    """
    Per-endpoint configuration for the SSRM engine.

    Args:
        fields:         List of FieldDef for all available columns.
        row_builder:    Callable(instance, List[FieldDef]) -> dict.
                        Serialises a model instance to a row dict.
                        If None, uses the built-in default builder.
        row_expander:   Optional Callable(instance, List[FieldDef]) -> List[dict].
                        When set, one DB instance can produce *multiple* output
                        rows (e.g. exploding a JSON array).  The engine switches
                        to virtual pagination (iterate-all, count expanded rows,
                        slice by start/end).  When None (default), the engine
                        uses fast queryset-level slicing (1 instance = 1 row).
        default_sort:   ORM order_by args when no sort is specified.
        search_fields:  ORM paths for free-text search on direct fields
                        (OR-combined icontains).  If None, search is disabled.
        search_json_config: Optional dict for searching inside JSON arrays.
                        Keys: ``table``, ``json_column``, ``array_path``,
                        ``fk_column``, ``search_columns`` (list of JSON keys).
                        When set, search also checks inside JSON array items.
        max_page_size:  Hard cap on rows per page.
    """
    fields: List[FieldDef]
    row_builder: Optional[Callable] = None
    row_expander: Optional[Callable] = None
    default_sort: list = dc_field(default_factory=lambda: ['-pk'])
    search_fields: Optional[List[str]] = None
    search_json_config: Optional[dict] = None
    max_page_size: int = 500

    def get_fields_dict(self) -> Dict[str, FieldDef]:
        """Return ``{col_id: FieldDef}`` mapping for fast lookup."""
        return {f.col_id: f for f in self.fields}


def default_row_builder(instance: Any, field_defs: List[FieldDef]) -> dict:
    """
    Default row serialiser.

    For each FieldDef:
    - If ``value_getter`` is set, call it with the instance.
    - Otherwise, traverse ``orm_path`` via attribute / dict access.
    """
    row: Dict[str, Any] = {}
    for fd in field_defs:
        if fd.value_getter:
            row[fd.col_id] = fd.value_getter(instance)
        else:
            row[fd.col_id] = _resolve_orm_path(instance, fd.orm_path)
    return row


def process_ssrm_request(
    config: SSRMConfig,
    ssrm_request: SSRMRequest,
    queryset: QuerySet,
) -> dict:
    """
    Main entry point: process an AG Grid SSRM request.

    1. Apply search (from ``extra`` params).
    2. Apply ``filterModel``.
    3. Route to grouped or flat handler.

    Returns ``{'rowData': [...], 'rowCount': N}``.
    """
    fields_dict = config.get_fields_dict()
    builder = config.row_builder or default_row_builder

    search_text = ssrm_request.extra.get('search', '')
    if search_text:
        queryset = _apply_full_search(
            queryset, search_text, config.search_fields, config.search_json_config,
        )

    queryset = apply_filters(queryset, ssrm_request.filter_model, fields_dict)

    if ssrm_request.is_grouping:
        return handle_grouped_request(
            queryset=queryset,
            ssrm_request=ssrm_request,
            fields_dict=fields_dict,
            row_builder=builder,
            field_defs=config.fields,
            default_sort=config.default_sort,
            max_page_size=config.max_page_size,
        )

    return _handle_flat(queryset, ssrm_request, config, fields_dict, builder)


def _apply_full_search(
    queryset: QuerySet,
    search_text: str,
    search_fields: Optional[List[str]],
    search_json_config: Optional[dict],
) -> QuerySet:
    """
    Search across direct ORM fields AND inside JSON arrays.

    Combines:
    1. ORM ``icontains`` on direct fields
    2. Raw SQL ``json_each`` + ``LIKE`` on JSON array items

    Results are OR-combined: a row matches if the search text appears
    in ANY direct field OR in ANY item's column values.
    """
    from django.db import connection
    from django.db.models import Q

    q = Q()

    if search_fields:
        for path in search_fields:
            q |= Q(**{f'{path}__icontains': search_text})

    if search_json_config:
        cfg = search_json_config
        table = cfg['table']
        json_col = cfg['json_column']
        array_path = cfg['array_path']
        fk_col = cfg['fk_column']
        columns = cfg.get('search_columns', [])

        if columns:
            concat_parts = ' || '.join(
                "COALESCE(CAST(json_extract(je.value, %s) AS TEXT), '')"
                for _ in columns
            )
            col_params = [f'$.{col}' for col in columns]

            inner_qs = queryset.values_list('id', flat=True)
            inner_sql, inner_params = inner_qs.query.sql_with_params()

            sql = f"""
                SELECT DISTINCT dd.{fk_col}
                FROM {table} dd, json_each(dd.{json_col}, '{array_path}') je
                WHERE dd.{fk_col} IN ({inner_sql})
                  AND ({concat_parts}) LIKE %s
            """
            all_params = list(inner_params) + col_params + [f'%{search_text}%']
            with connection.cursor() as cursor:
                cursor.execute(sql, all_params)
                json_match_ids = [row[0] for row in cursor.fetchall()]

            if json_match_ids:
                q |= Q(id__in=json_match_ids)

    if q:
        return queryset.filter(q)
    return queryset


def _handle_flat(
    queryset: QuerySet,
    ssrm_request: SSRMRequest,
    config: SSRMConfig,
    fields_dict: Dict[str, FieldDef],
    builder: Callable,
) -> dict:
    """Sort, paginate, and serialise flat (non-grouped) rows."""
    order = get_order_fields(
        ssrm_request.sort_model, fields_dict, config.default_sort,
    )

    if config.row_expander:
        return _handle_flat_expanded(
            queryset, ssrm_request, config, order,
        )

    total = queryset.count()
    start = ssrm_request.start_row
    end = min(ssrm_request.end_row, start + config.max_page_size)
    page = queryset.order_by(*order)[start:end]
    row_data = [builder(obj, config.fields) for obj in page]
    return {'rowData': row_data, 'rowCount': total}


def _handle_flat_expanded(
    queryset: QuerySet,
    ssrm_request: SSRMRequest,
    config: SSRMConfig,
    order: List[str],
) -> dict:
    """
    Virtual pagination for row_expander mode.

    One DB instance can produce N output rows, so we can't use queryset
    slicing.  Computes total via DB when possible, then iterates only
    enough rows to fill the requested page.
    """
    expander = config.row_expander
    start = ssrm_request.start_row
    page_size = min(ssrm_request.page_size, config.max_page_size)

    total_rows = _expanded_total_count(queryset, config)
    can_break_early = total_rows is not None

    data_list: List[dict] = []
    virtual_idx = 0

    for instance in queryset.order_by(*order).iterator():
        rows = expander(instance, config.fields)  # type: ignore
        n = len(rows)
        instance_start = virtual_idx
        virtual_idx += n

        if virtual_idx <= start:
            continue

        if len(data_list) >= page_size:
            if can_break_early:
                break
            continue

        for i, row in enumerate(rows):
            idx = instance_start + i
            if idx >= start and len(data_list) < page_size:
                data_list.append(row)

    if total_rows is None:
        total_rows = virtual_idx

    return {'rowData': data_list, 'rowCount': total_rows}


def _expanded_total_count(
    queryset: QuerySet, config: SSRMConfig,
) -> Optional[int]:
    """
    Compute the total expanded row count at the DB level using
    ``json_array_length``.  Returns None if not possible (no json_array_config).
    """
    from django.db import connection

    cfg = None
    for fd in config.fields:
        if fd.is_json and fd.json_array_config:
            cfg = fd.json_array_config
            break
    if not cfg:
        return None

    table = cfg['table']
    json_col = cfg['json_column']
    array_path = cfg['array_path']
    fk_col = cfg['fk_column']

    inner_sql, inner_params = queryset.values_list('id', flat=True).query.sql_with_params()

    sql = f"""
        SELECT COALESCE(SUM(
            CASE WHEN json_type(dd.{json_col}, '{array_path}') = 'array'
                 THEN json_array_length(dd.{json_col}, '{array_path}')
                 ELSE 1 END
        ), 0)
        FROM {table} dd
        WHERE dd.{fk_col} IN ({inner_sql})
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, inner_params)
        row = cursor.fetchone()
        return row[0] if row else 0


def _resolve_orm_path(instance: Any, orm_path: str) -> Any:
    """
    Traverse a Django ORM-style path on a model instance.

    ``'data__payload__name'``  becomes
    ``instance.data.payload['name']``
    (switches to dict-key access after hitting a dict).
    """
    obj = instance
    for part in orm_path.split('__'):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            obj = getattr(obj, part, None)
    return obj
