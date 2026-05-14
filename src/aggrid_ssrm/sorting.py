"""
AG Grid sortModel → Django ORM order_by translation.
"""
from typing import Dict, List

from .fields import FieldDef


def get_order_fields(
    sort_model: List[Dict[str, str]],
    fields_dict: Dict[str, FieldDef],
    default_sort: List[str],
) -> List[str]:
    """
    Convert AG Grid ``sortModel`` to a list of Django ``order_by()`` arguments.

    Each entry ``{colId, sort: 'asc'|'desc'}`` is resolved through the
    FieldDef to get the ORM path and prefixed with ``-`` for descending.

    Returns *default_sort* if no valid sort fields are found.
    """
    order_fields: List[str] = []
    for entry in sort_model:
        col_id = entry.get('colId', '')
        field_def = fields_dict.get(col_id)
        if not field_def or not field_def.sortable:
            continue
        prefix = '-' if entry.get('sort') == 'desc' else ''
        order_fields.append(f'{prefix}{field_def.orm_path}')
    return order_fields or list(default_sort)
