"""
Distinct column values for AG Grid Set Filter dropdown.
"""
from typing import Dict, List

from django.db import connection
from django.db.models import QuerySet

from .fields import FieldDef


DEFAULT_LIMIT = 500


def get_distinct_values(
    queryset: QuerySet,
    col_id: str,
    fields_dict: Dict[str, FieldDef],
    limit: int = DEFAULT_LIMIT,
) -> List:
    """
    Return sorted distinct values for a column, capped at ``limit``.

    For non-JSON fields uses DB-level ``DISTINCT``.
    For JSON fields uses raw SQL with ``json_each`` to extract values
    from inside JSON arrays (handles nested ``items[]`` structures).
    Falls back to ORM when the field is a top-level JSON key.
    """
    fd = fields_dict.get(col_id)
    if not fd:
        return []

    if fd.is_json:
        return _distinct_json(queryset, fd, limit)

    qs = (
        queryset
        .values_list(fd.orm_path, flat=True)
        .exclude(**{f'{fd.orm_path}__isnull': True})
    )
    # Empty-string exclusion only applies to text-like fields; on numeric
    # and date columns, Django rejects '' at validate-time.
    if fd.field_type in ('text', 'set'):
        qs = qs.exclude(**{fd.orm_path: ''})
    return list(qs.distinct().order_by(fd.orm_path)[:limit])


def _distinct_json(queryset: QuerySet, fd: FieldDef, limit: int) -> List:
    """
    Extract distinct values for a JSON field, capped at ``limit``.

    Strategy (in order of preference):
    1. Raw SQL ``json_each`` via ``json_array_config`` (DB-level, scalable)
    2. ORM path (fast, works for simple top-level JSON keys)
    3. Python ``value_getter`` iteration (correct but slow for large datasets)
    """
    if fd.json_array_config:
        return _distinct_json_array_sql(queryset, fd, limit)

    if _is_safe_orm_field(fd.orm_path):
        try:
            sample = list(queryset.values_list(fd.orm_path, flat=True)[:1])
            if sample and sample[0] is not None:
                return sorted(set(
                    str(v) for v in
                    queryset.values_list(fd.orm_path, flat=True)
                    if v is not None and v != ''
                ))[:limit]
        except (ValueError, Exception):
            pass

    if fd.value_getter:
        return _distinct_json_getter(queryset, fd, limit)

    return []


def _is_safe_orm_field(orm_path: str) -> bool:
    """Check if an ORM path is safe for Django's values_list (no special chars)."""
    last_part = orm_path.split('__')[-1]
    return last_part.isidentifier()


def _distinct_json_array_sql(queryset: QuerySet, fd: FieldDef, limit: int = DEFAULT_LIMIT) -> List:
    """
    Use raw SQL ``json_each`` to extract distinct values from
    inside a JSON array.  Driven by ``fd.json_array_config``.

    Uses a compiled subquery instead of materialising IDs to avoid
    SQLite's 999-variable limit and memory issues at scale.
    """
    cfg = fd.json_array_config
    table = cfg['table']
    json_col = cfg['json_column']
    array_path = cfg['array_path']
    fk_col = cfg['fk_column']
    col_name = fd.col_id

    inner_sql, inner_params = _compile_id_subquery(queryset)

    json_path = f'$.{col_name}'
    sql = f"""
        SELECT DISTINCT json_extract(je.value, %s) AS val
        FROM {table} dd,
             json_each(dd.{json_col}, '{array_path}') je
        WHERE dd.{fk_col} IN ({inner_sql})
          AND val IS NOT NULL
          AND val != ''
        ORDER BY val
        LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [json_path] + list(inner_params) + [limit])
        return [str(row[0]) for row in cursor.fetchall()]


def _compile_id_subquery(queryset: QuerySet):
    """Compile a queryset into a SQL subquery for use in WHERE ... IN (...)."""
    inner_qs = queryset.values_list('id', flat=True)
    return inner_qs.query.sql_with_params()


def _distinct_json_getter(queryset: QuerySet, fd: FieldDef, limit: int = DEFAULT_LIMIT) -> List:
    """
    Python fallback: iterate instances and use ``value_getter``.
    Flattens array return values.
    """
    unique = set()
    for instance in queryset.only('id').iterator():
        val = fd.value_getter(instance)
        if val is None:
            continue
        if isinstance(val, list):
            for v in val:
                if v is not None and v != '':
                    unique.add(str(v))
        elif val != '':
            unique.add(str(val))
            if len(unique) >= limit * 2:
                break
    return sorted(unique)[:limit]
