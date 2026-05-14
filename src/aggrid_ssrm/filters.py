"""
AG Grid filter model → Django ORM queryset filters.

Supports all AG Grid filter types:
  - Set:    {filterType:'set', values:[...]}
  - Text:   {filterType:'text', type:'contains', filter:'x'}
  - Number: {filterType:'number', type:'greaterThan', filter:N}
  - Date:   {filterType:'date', type:'inRange', dateFrom:'...', dateTo:'...'}
  - Combined: {operator:'AND'|'OR', condition1:{...}, condition2:{...}}
"""
from typing import Any, Dict, List, Optional

from django.db import connection
from django.db.models import Q, QuerySet

from .fields import FieldDef


def apply_filters(
    queryset: QuerySet,
    filter_model: Dict[str, Any],
    fields_dict: Dict[str, FieldDef],
) -> QuerySet:
    """Apply the full AG Grid filterModel to a queryset."""
    for col_id, filter_spec in filter_model.items():
        field_def = fields_dict.get(col_id)
        if not field_def or not field_def.filterable:
            continue
        queryset = _apply_single_filter(queryset, field_def, filter_spec)
    return queryset


def apply_search(
    queryset: QuerySet,
    search_text: str,
    search_fields: List[str],
) -> QuerySet:
    """Free-text search across multiple ORM fields (OR-combined icontains)."""
    if not search_text or not search_fields:
        return queryset
    q = Q()
    for path in search_fields:
        q |= Q(**{f'{path}__icontains': search_text})
    return queryset.filter(q)


def _apply_single_filter(
    queryset: QuerySet, field_def: FieldDef, spec: dict,
) -> QuerySet:
    """Route to the correct handler based on filterType or combined operator."""
    orm_path = field_def.orm_path

    if field_def.json_array_config:
        return _apply_json_array_filter(queryset, field_def, spec)

    if 'operator' in spec:
        return _apply_combined_filter(queryset, orm_path, spec)

    filter_type = spec.get('filterType', 'text')
    handler = _FILTER_HANDLERS.get(filter_type)
    if handler:
        return handler(queryset, orm_path, spec)
    return queryset


def _apply_combined_filter(
    queryset: QuerySet, orm_path: str, spec: dict,
) -> QuerySet:
    """Handle {operator:'AND'|'OR', condition1:{…}, condition2:{…}}."""
    op = spec.get('operator', 'AND')
    q1 = _spec_to_q(orm_path, spec.get('condition1', {}))
    q2 = _spec_to_q(orm_path, spec.get('condition2', {}))

    if q1 is None and q2 is None:
        return queryset
    if q1 is None:
        return queryset.filter(q2)
    if q2 is None:
        return queryset.filter(q1)

    combined = (q1 | q2) if op == 'OR' else (q1 & q2)
    return queryset.filter(combined)


def _spec_to_q(orm_path: str, spec: dict) -> Optional[Q]:
    """Convert a single condition spec to a Q object (or None)."""
    filter_type = spec.get('filterType', 'text')
    handler = _Q_HANDLERS.get(filter_type)
    return handler(orm_path, spec) if handler else None


def _apply_set_filter(queryset: QuerySet, orm_path: str, spec: dict) -> QuerySet:
    values = spec.get('values')
    if values is None:
        return queryset
    return queryset.filter(**{f'{orm_path}__in': values})


def _set_q(orm_path: str, spec: dict) -> Optional[Q]:
    values = spec.get('values')
    if values is None:
        return None
    return Q(**{f'{orm_path}__in': values})


def _apply_text_filter(queryset: QuerySet, orm_path: str, spec: dict) -> QuerySet:
    q = _text_q(orm_path, spec)
    return queryset.filter(q) if q else queryset


def _text_q(orm_path: str, spec: dict) -> Optional[Q]:
    op = spec.get('type', 'contains')
    val = spec.get('filter', '')

    if op == 'contains':
        return Q(**{f'{orm_path}__icontains': val})
    if op == 'notContains':
        return ~Q(**{f'{orm_path}__icontains': val})
    if op == 'equals':
        return Q(**{f'{orm_path}__iexact': val})
    if op == 'notEqual':
        return ~Q(**{f'{orm_path}__iexact': val})
    if op == 'startsWith':
        return Q(**{f'{orm_path}__istartswith': val})
    if op == 'endsWith':
        return Q(**{f'{orm_path}__iendswith': val})
    if op == 'blank':
        return Q(**{f'{orm_path}__isnull': True}) | Q(**{orm_path: ''})
    if op == 'notBlank':
        return Q(**{f'{orm_path}__isnull': False}) & ~Q(**{orm_path: ''})
    return None


def _apply_number_filter(queryset: QuerySet, orm_path: str, spec: dict) -> QuerySet:
    q = _number_q(orm_path, spec)
    return queryset.filter(q) if q else queryset


def _number_q(orm_path: str, spec: dict) -> Optional[Q]:
    op = spec.get('type', 'equals')
    val = spec.get('filter')
    val_to = spec.get('filterTo')

    if op == 'equals':
        return Q(**{orm_path: val})
    if op == 'notEqual':
        return ~Q(**{orm_path: val})
    if op == 'greaterThan':
        return Q(**{f'{orm_path}__gt': val})
    if op == 'greaterThanOrEqual':
        return Q(**{f'{orm_path}__gte': val})
    if op == 'lessThan':
        return Q(**{f'{orm_path}__lt': val})
    if op == 'lessThanOrEqual':
        return Q(**{f'{orm_path}__lte': val})
    if op == 'inRange' and val is not None and val_to is not None:
        return Q(**{f'{orm_path}__gte': val, f'{orm_path}__lte': val_to})
    if op == 'blank':
        return Q(**{f'{orm_path}__isnull': True})
    if op == 'notBlank':
        return Q(**{f'{orm_path}__isnull': False})
    return None


def _apply_date_filter(queryset: QuerySet, orm_path: str, spec: dict) -> QuerySet:
    q = _date_q(orm_path, spec)
    return queryset.filter(q) if q else queryset


def _date_q(orm_path: str, spec: dict) -> Optional[Q]:
    op = spec.get('type', 'equals')
    date_from = spec.get('dateFrom')
    date_to = spec.get('dateTo')

    if op == 'equals' and date_from:
        return Q(**{f'{orm_path}__date': date_from})
    if op == 'notEqual' and date_from:
        return ~Q(**{f'{orm_path}__date': date_from})
    if op == 'greaterThan' and date_from:
        return Q(**{f'{orm_path}__date__gt': date_from})
    if op == 'lessThan' and date_from:
        return Q(**{f'{orm_path}__date__lt': date_from})
    if op == 'inRange' and date_from and date_to:
        return Q(**{f'{orm_path}__date__gte': date_from,
                     f'{orm_path}__date__lte': date_to})
    if op == 'blank':
        return Q(**{f'{orm_path}__isnull': True})
    if op == 'notBlank':
        return Q(**{f'{orm_path}__isnull': False})
    return None


def _apply_json_array_filter(
    queryset: QuerySet, field_def: FieldDef, spec: dict,
) -> QuerySet:
    """
    Filter using raw SQL ``json_each`` for values nested inside a JSON array.

    Builds: WHERE id IN (SELECT fk FROM table, json_each(...) WHERE json_extract(...) <condition>)
    """
    cfg = field_def.json_array_config
    table = cfg['table']
    json_col = cfg['json_column']
    array_path = cfg['array_path']
    fk_col = cfg['fk_column']
    col_name = field_def.col_id

    if 'operator' in spec:
        op = spec.get('operator', 'AND')
        c1 = spec.get('condition1', {})
        c2 = spec.get('condition2', {})
        qs = queryset
        if op == 'AND':
            if c1:
                qs = _apply_json_array_filter(qs, field_def, c1)
            if c2:
                qs = _apply_json_array_filter(qs, field_def, c2)
        else:
            ids1 = _json_array_matching_ids(qs, field_def, c1) if c1 else set()
            ids2 = _json_array_matching_ids(qs, field_def, c2) if c2 else set()
            combined = ids1 | ids2
            if combined:
                qs = qs.filter(id__in=combined)
            else:
                qs = qs.none()
        return qs

    filter_type = spec.get('filterType', 'text')

    json_path = f'$.{col_name}'

    if filter_type == 'set':
        values = spec.get('values')
        if values is None:
            return queryset
        placeholders = ','.join(['%s'] * len(values))
        condition = f"json_extract(je.value, %s) IN ({placeholders})"
        params = [json_path] + list(values)
    elif filter_type == 'text':
        condition, params = _json_text_condition(json_path, spec)
    elif filter_type == 'number':
        condition, params = _json_number_condition(json_path, spec)
    else:
        return queryset

    if not condition:
        return queryset

    sql = f"""
        SELECT DISTINCT dd.{fk_col}
        FROM {table} dd, json_each(dd.{json_col}, '{array_path}') je
        WHERE {condition}
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        matching_ids = [row[0] for row in cursor.fetchall()]

    if not matching_ids:
        return queryset.none()
    return queryset.filter(id__in=matching_ids)


def _json_array_matching_ids(queryset, field_def, spec):
    """Helper for OR combined: get IDs matching a single condition."""
    filtered = _apply_json_array_filter(queryset, field_def, spec)
    return set(filtered.values_list('id', flat=True))


def _json_text_condition(json_path: str, spec: dict):
    op = spec.get('type', 'contains')
    val = spec.get('filter', '')
    extract = "json_extract(je.value, %s)"

    if op == 'contains':
        return f"{extract} LIKE %s", [json_path, f'%{val}%']
    if op == 'notContains':
        return f"{extract} NOT LIKE %s", [json_path, f'%{val}%']
    if op == 'equals':
        return f"{extract} = %s", [json_path, val]
    if op == 'notEqual':
        return f"{extract} != %s", [json_path, val]
    if op == 'startsWith':
        return f"{extract} LIKE %s", [json_path, f'{val}%']
    if op == 'endsWith':
        return f"{extract} LIKE %s", [json_path, f'%{val}']
    if op == 'blank':
        return f"({extract} IS NULL OR {extract} = '')", [json_path, json_path]
    if op == 'notBlank':
        return f"({extract} IS NOT NULL AND {extract} != '')", [json_path, json_path]
    return None, []


def _json_number_condition(json_path: str, spec: dict):
    op = spec.get('type', 'equals')
    val = spec.get('filter')
    val_to = spec.get('filterTo')
    extract = "CAST(json_extract(je.value, %s) AS REAL)"

    if op == 'equals':
        return f"{extract} = %s", [json_path, val]
    if op == 'notEqual':
        return f"{extract} != %s", [json_path, val]
    if op == 'greaterThan':
        return f"{extract} > %s", [json_path, val]
    if op == 'greaterThanOrEqual':
        return f"{extract} >= %s", [json_path, val]
    if op == 'lessThan':
        return f"{extract} < %s", [json_path, val]
    if op == 'lessThanOrEqual':
        return f"{extract} <= %s", [json_path, val]
    if op == 'inRange' and val is not None and val_to is not None:
        return f"{extract} >= %s AND {extract} <= %s", [json_path, val, json_path, val_to]
    if op == 'blank':
        return f"json_extract(je.value, %s) IS NULL", [json_path]
    if op == 'notBlank':
        return f"json_extract(je.value, %s) IS NOT NULL", [json_path]
    return None, []


_FILTER_HANDLERS = {
    'set':    _apply_set_filter,
    'text':   _apply_text_filter,
    'number': _apply_number_filter,
    'date':   _apply_date_filter,
}

_Q_HANDLERS = {
    'set':    _set_q,
    'text':   _text_q,
    'number': _number_q,
    'date':   _date_q,
}
