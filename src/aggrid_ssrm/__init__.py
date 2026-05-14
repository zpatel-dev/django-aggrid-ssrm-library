"""
AG Grid Server-Side Row Model (SSRM) adapter for Django.

This library provides the server-side protocol implementation that
AG Grid Enterprise's SSRM expects: filter / sort / group / paginate
translation from grid requests into Django ORM operations.

Note: AG Grid SSRM is an Enterprise-only feature of AG Grid.  This
library is independent of AG Grid Ltd. and released under the MIT
License; you still need a valid AG Grid Enterprise license to use
SSRM in production.  See https://www.ag-grid.com/license-pricing/.

Usage::

    from aggrid_ssrm import (
        SSRMConfig, SSRMRequest, FieldDef, process_ssrm_request,
    )

    config = SSRMConfig(
        fields=[
            FieldDef('name', 'name'),
            FieldDef('status', 'status', field_type='set'),
            FieldDef('score', 'metadata__score', field_type='number', is_json=True),
        ],
        search_fields=['name', 'status'],
        default_sort=['-pk'],
    )

    ssrm_req = SSRMRequest.from_body(json.loads(request.body))
    queryset = MyModel.objects.all()
    result = process_ssrm_request(config, ssrm_req, queryset)
    return JsonResponse(result)   # {'rowData': [...], 'rowCount': N}
"""

from .column_values import get_distinct_values
from .engine import SSRMConfig, default_row_builder, process_ssrm_request
from .fields import FieldDef
from .filters import apply_filters, apply_search
from .request import SSRMRequest

__version__ = "0.1.0"

__all__ = [
    'FieldDef',
    'SSRMRequest',
    'SSRMConfig',
    'process_ssrm_request',
    'default_row_builder',
    'get_distinct_values',
    'apply_filters',
    'apply_search',
    '__version__',
]

default_app_config = 'aggrid_ssrm.apps.AggridSsrmConfig'
