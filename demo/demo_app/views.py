"""Demo views — index page + SSRM endpoint + column-values endpoint."""
import json

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from aggrid_ssrm import (
    FieldDef,
    SSRMConfig,
    SSRMRequest,
    get_distinct_values,
    process_ssrm_request,
)

from .models import Sale


def _build_config() -> SSRMConfig:
    """SSRMConfig describing the columns AG Grid is allowed to query."""
    return SSRMConfig(
        fields=[
            FieldDef('id', 'id', field_type='number',
                     groupable=False, filterable=False),
            FieldDef('region', 'region', field_type='set'),
            FieldDef('product', 'product', field_type='text'),
            FieldDef('category', 'category', field_type='set'),
            FieldDef('quantity', 'quantity', field_type='number',
                     groupable=False),
            FieldDef('unit_price', 'unit_price', field_type='number',
                     groupable=False),
            FieldDef('sold_at', 'sold_at', field_type='date',
                     groupable=False),
            FieldDef('sales_rep', 'sales_rep', field_type='text'),
        ],
        default_sort=['-sold_at'],
        search_fields=['product', 'sales_rep', 'region'],
    )


def index(request):
    column_defs = [
        {'field': 'id', 'maxWidth': 90, 'filter': 'agNumberColumnFilter'},
        {'field': 'region', 'filter': 'agSetColumnFilter', 'enableRowGroup': True},
        {'field': 'product', 'filter': 'agTextColumnFilter'},
        {'field': 'category', 'filter': 'agSetColumnFilter', 'enableRowGroup': True},
        {'field': 'quantity', 'filter': 'agNumberColumnFilter', 'aggFunc': 'sum'},
        {'field': 'unit_price', 'filter': 'agNumberColumnFilter', 'aggFunc': 'avg'},
        {'field': 'sold_at', 'filter': 'agDateColumnFilter', 'sort': 'desc'},
        {'field': 'sales_rep', 'filter': 'agTextColumnFilter'},
    ]
    return render(request, 'demo_app/index.html', {
        'column_defs_json': json.dumps(column_defs),
        'ag_grid_license_key': getattr(settings, 'AG_GRID_LICENSE_KEY', ''),
    })


@csrf_exempt
@require_POST
def sales_ssrm(request):
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON')
    ssrm_req = SSRMRequest.from_body(body)
    config = _build_config()
    result = process_ssrm_request(config, ssrm_req, Sale.objects.all())
    return JsonResponse(result)


@require_GET
def sales_column_values(request):
    col_id = request.GET.get('column', '')
    if not col_id:
        return HttpResponseBadRequest("Missing 'column' query parameter")
    try:
        limit = int(request.GET.get('limit', 500))
    except ValueError:
        return HttpResponseBadRequest("Invalid 'limit'")
    config = _build_config()
    values = get_distinct_values(
        Sale.objects.all(), col_id, config.get_fields_dict(), limit=limit,
    )
    return JsonResponse({'values': values})
