"""
FieldDef — maps an AG Grid column to a Django ORM lookup path.

Each grid column is described by one FieldDef that tells the SSRM engine
how to filter, sort, group, and serialize that column.
"""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class FieldDef:
    """
    Configuration for a single AG Grid column.

    Args:
        col_id:       AG Grid colId / field name (e.g. 'name', 'region').
        orm_path:     Django ORM lookup path (e.g. 'name',
                      'data__payload__region').
        field_type:   One of 'text', 'number', 'date', 'set'. Controls which
                      filter operators are valid. Defaults to 'text'.
        is_json:      Whether this field lives inside a JSONField. When True,
                      grouping falls back to Python-level aggregation for
                      SQLite compatibility.
        sortable:     Whether this field can be sorted.
        filterable:   Whether this field can be filtered.
        groupable:    Whether this field can be used for row grouping.
        value_getter: Optional callable(instance) -> value for custom row
                      serialization.  If None, the default row builder
                      traverses orm_path via attribute/dict access.
        json_array_config: Optional dict for raw-SQL JSON array extraction.
                      When set, enables DB-level ``json_each`` for grouping
                      and distinct values instead of Python iteration.
                      Keys: ``table`` (e.g. 'myapp_itemdata'),
                      ``json_column`` (e.g. 'payload'),
                      ``array_path`` (e.g. '$.items'),
                      ``fk_column`` (e.g. 'item_id').
    """
    col_id: str
    orm_path: str
    field_type: str = 'text'
    is_json: bool = False
    sortable: bool = True
    filterable: bool = True
    groupable: bool = True
    value_getter: Optional[Callable] = None
    json_array_config: Optional[dict] = None
