"""
AG Grid SSRM grouping — aggregated group rows and drill-down.
"""
import json as _json
from collections import Counter
from typing import Callable, Dict, List

from django.db.models import Avg, Count, Max, Min, QuerySet, Sum

from .fields import FieldDef
from .request import SSRMRequest
from .sorting import get_order_fields

AGG_FUNCS = {
    'sum':   Sum,
    'avg':   Avg,
    'count': Count,
    'min':   Min,
    'max':   Max,
}


def handle_grouped_request(
    queryset: QuerySet,
    ssrm_request: SSRMRequest,
    fields_dict: Dict[str, FieldDef],
    row_builder: Callable,
    field_defs: list,
    default_sort: List[str],
    max_page_size: int = 500,
) -> dict:
    """
    Process a grouped SSRM request.

    1. Drill down through parent ``groupKeys``.
    2. If at a non-leaf level, return aggregated group rows with childCount.
    3. If at leaf level, return actual data rows.

    Returns ``{'rowData': [...], 'rowCount': N}``.
    """
    queryset = _apply_group_key_filters(
        queryset,
        ssrm_request.row_group_cols,
        ssrm_request.group_keys,
        fields_dict,
    )

    level = ssrm_request.group_level

    if level < len(ssrm_request.row_group_cols):
        group_col = ssrm_request.row_group_cols[level]
        group_field = fields_dict.get(group_col.get('field', ''))
        if not group_field or not group_field.groupable:
            return {'rowData': [], 'rowCount': 0}

        start = ssrm_request.start_row
        end = min(ssrm_request.end_row, start + max_page_size)

        if group_field.is_json:
            return _aggregate_python(
                queryset, group_field, start, end,
            )
        return _aggregate_orm(
            queryset, group_field,
            ssrm_request.value_cols, fields_dict,
            start, end,
        )

    order = get_order_fields(ssrm_request.sort_model, fields_dict, default_sort)
    total = queryset.count()
    start = ssrm_request.start_row
    end = min(ssrm_request.end_row, start + max_page_size)
    page = queryset.order_by(*order)[start:end]
    row_data = [row_builder(obj, field_defs) for obj in page]
    return {'rowData': row_data, 'rowCount': total}


def _apply_group_key_filters(
    queryset: QuerySet,
    row_group_cols: List[Dict[str, str]],
    group_keys: List[str],
    fields_dict: Dict[str, FieldDef],
) -> QuerySet:
    """Filter queryset by each parent group key in the drill-down path."""
    for i, key in enumerate(group_keys):
        col_field = row_group_cols[i].get('field', '')
        fd = fields_dict.get(col_field)
        if fd:
            queryset = queryset.filter(**{fd.orm_path: _coerce_key(key, fd)})
    return queryset


def _coerce_key(key, fd: FieldDef):
    """
    AG Grid sends group keys as strings.  For JSON fields that store
    native types (int, float, bool), coerce the string back so the
    ORM filter matches the actual stored value.
    """
    if not fd.is_json or not isinstance(key, str):
        return key
    try:
        return _json.loads(key)
    except (ValueError, TypeError):
        return key


def _aggregate_orm(
    queryset: QuerySet,
    group_field: FieldDef,
    value_cols: List[Dict[str, str]],
    fields_dict: Dict[str, FieldDef],
    start_row: int,
    end_row: int,
) -> dict:
    """
    ORM-level GROUP BY for direct (non-JSON) fields.

    Adds ``childCount`` plus any valueCols aggregations (sum, avg, etc.).
    """
    orm_path = group_field.orm_path
    groups = queryset.values(orm_path).annotate(childCount=Count('id'))

    for vc in value_cols:
        vc_fd = fields_dict.get(vc.get('field', ''))
        agg_name = vc.get('aggFunc', 'count')
        agg_cls = AGG_FUNCS.get(agg_name)
        if vc_fd and agg_cls and not vc_fd.is_json:
            alias = vc_fd.col_id
            groups = groups.annotate(**{alias: agg_cls(vc_fd.orm_path)})

    groups = groups.order_by(orm_path)
    total = groups.count()
    page = list(groups[start_row:end_row])

    row_data = []
    for g in page:
        row = {group_field.col_id: g[orm_path], 'childCount': g['childCount']}
        for vc in value_cols:
            vc_id = vc.get('field', '')
            if vc_id in g:
                row[vc_id] = g[vc_id]
        row_data.append(row)

    return {'rowData': row_data, 'rowCount': total}


def _aggregate_python(
    queryset: QuerySet,
    group_field: FieldDef,
    start_row: int,
    end_row: int,
) -> dict:
    """
    Python-level grouping for JSON fields (SQLite compatibility).

    Strategy (in order of preference):
    1. ORM ``values_list`` (fast, for top-level JSON keys)
    2. Raw SQL ``json_each`` via ``json_array_config`` (DB-level, scalable)
    3. Python ``value_getter`` iteration (correct but slow)
    """
    if group_field.json_array_config:
        return _aggregate_json_array_sql(
            queryset, group_field, start_row, end_row,
        )

    last_part = group_field.orm_path.split('__')[-1]
    if last_part.isidentifier():
        try:
            sample = list(queryset.values_list(group_field.orm_path, flat=True)[:1])
            if sample and sample[0] is not None:
                counter: Counter = Counter()
                for v in queryset.values_list(group_field.orm_path, flat=True):
                    if v is not None:
                        counter[str(v)] += 1
                return _paginate_counter(counter, group_field.col_id, start_row, end_row)
        except (ValueError, Exception):
            pass

    if group_field.value_getter:
        counter = Counter()
        for instance in queryset.iterator():
            val = group_field.value_getter(instance)
            if val is None:
                continue
            if isinstance(val, list):
                for v in val:
                    if v is not None:
                        counter[str(v)] += 1
            else:
                counter[str(val)] += 1
        return _paginate_counter(counter, group_field.col_id, start_row, end_row)

    return {'rowData': [], 'rowCount': 0}


def _paginate_counter(counter: Counter, col_id: str, start: int, end: int) -> dict:
    sorted_groups = sorted(counter.items(), key=lambda x: x[0])
    total = len(sorted_groups)
    page = sorted_groups[start:end]
    return {
        'rowData': [{col_id: val, 'childCount': cnt} for val, cnt in page],
        'rowCount': total,
    }


def _aggregate_json_array_sql(
    queryset: QuerySet,
    group_field: FieldDef,
    start_row: int,
    end_row: int,
) -> dict:
    """
    Use raw SQL ``json_each`` to group and count values nested inside
    a JSON array.  All work done in the DB.  Driven by ``json_array_config``.

    Uses a compiled subquery instead of materialising IDs to avoid
    SQLite's 999-variable limit and memory issues at scale.
    """
    from django.db import connection

    cfg = group_field.json_array_config or {}
    table = cfg.get('table', '')
    json_col = cfg.get('json_column', '')
    array_path = cfg.get('array_path', '')
    fk_col = cfg.get('fk_column', '')
    col_name = group_field.col_id

    inner_sql, inner_params = _compile_id_subquery(queryset)
    json_path = f'$.{col_name}'

    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT json_extract(je.value, %s) AS val
            FROM {table} dd,
                 json_each(dd.{json_col}, '{array_path}') je
            WHERE dd.{fk_col} IN ({inner_sql})
              AND val IS NOT NULL AND val != ''
        )
    """
    data_sql = f"""
        SELECT val, COUNT(*) AS cnt FROM (
            SELECT json_extract(je.value, %s) AS val
            FROM {table} dd,
                 json_each(dd.{json_col}, '{array_path}') je
            WHERE dd.{fk_col} IN ({inner_sql})
              AND json_extract(je.value, %s) IS NOT NULL
              AND json_extract(je.value, %s) != ''
        )
        GROUP BY val
        ORDER BY val
        LIMIT %s OFFSET %s
    """

    with connection.cursor() as cursor:
        cursor.execute(count_sql, [json_path] + list(inner_params))
        row = cursor.fetchone()
        total = row[0] if row else 0

        page_size = end_row - start_row
        cursor.execute(data_sql, [json_path] + list(inner_params) + [json_path, json_path, page_size, start_row])
        rows = cursor.fetchall()

    row_data = [
        {group_field.col_id: str(val), 'childCount': cnt}
        for val, cnt in rows
    ]
    return {'rowData': row_data, 'rowCount': total}


def _compile_id_subquery(queryset: QuerySet):
    """Compile a queryset into a SQL subquery for use in WHERE ... IN (...)."""
    inner_qs = queryset.values_list('id', flat=True)
    return inner_qs.query.sql_with_params()
