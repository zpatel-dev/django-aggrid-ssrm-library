"""
SSRMRequest — parsed and validated AG Grid Server-Side Row Model request.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


KNOWN_KEYS = {
    'startRow', 'endRow', 'rowGroupCols', 'groupKeys',
    'valueCols', 'pivotCols', 'pivotMode',
    'filterModel', 'sortModel',
}


@dataclass
class SSRMRequest:
    """
    Typed representation of an AG Grid SSRM request body.

    Known AG Grid keys are extracted into typed fields.
    Everything else (app-specific params like ``search``, ``explode``)
    goes into ``extra``.
    """
    start_row: int = 0
    end_row: int = 100
    row_group_cols: List[Dict[str, str]] = field(default_factory=list)
    group_keys: List[str] = field(default_factory=list)
    value_cols: List[Dict[str, str]] = field(default_factory=list)
    pivot_cols: List[Dict[str, str]] = field(default_factory=list)
    pivot_mode: bool = False
    filter_model: Dict[str, Any] = field(default_factory=dict)
    sort_model: List[Dict[str, str]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_grouping(self) -> bool:
        return len(self.row_group_cols) > 0

    @property
    def group_level(self) -> int:
        return len(self.group_keys)

    @property
    def is_leaf_level(self) -> bool:
        return self.group_level >= len(self.row_group_cols)

    @property
    def page_size(self) -> int:
        return self.end_row - self.start_row

    @classmethod
    def from_body(cls, body: dict) -> 'SSRMRequest':
        """Parse a raw POST JSON body into an SSRMRequest."""
        extra = {k: v for k, v in body.items() if k not in KNOWN_KEYS}
        return cls(
            start_row=body.get('startRow', 0),
            end_row=body.get('endRow', 100),
            row_group_cols=body.get('rowGroupCols', []),
            group_keys=body.get('groupKeys', []),
            value_cols=body.get('valueCols', []),
            pivot_cols=body.get('pivotCols', []),
            pivot_mode=body.get('pivotMode', False),
            filter_model=body.get('filterModel', {}),
            sort_model=body.get('sortModel', []),
            extra=extra,
        )
