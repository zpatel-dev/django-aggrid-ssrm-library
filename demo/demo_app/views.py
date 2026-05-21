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

from .models import AthleteEvent


def _build_config() -> SSRMConfig:
    """SSRMConfig describing the columns AG Grid is allowed to query."""
    return SSRMConfig(
        fields=[
            FieldDef('name',   'name',   field_type='text'),
            FieldDef('sex',    'sex',    field_type='set'),
            FieldDef('age',    'age',    field_type='number', groupable=False),
            FieldDef('height', 'height', field_type='number', groupable=False),
            FieldDef('weight', 'weight', field_type='number', groupable=False),
            FieldDef('team',   'team',   field_type='text'),
            FieldDef('noc',    'noc',    field_type='set'),
            FieldDef('games',  'games',  field_type='set'),
            FieldDef('year',   'year',   field_type='number'),
            FieldDef('season', 'season', field_type='set'),
            FieldDef('city',   'city',   field_type='set'),
            FieldDef('sport',  'sport',  field_type='set'),
            FieldDef('event',  'event',  field_type='text'),
            FieldDef('medal',  'medal',  field_type='set'),
        ],
        default_sort=['-year', 'name'],
        search_fields=['name', 'team', 'sport', 'event'],
    )


def index(request):
    column_defs = [
        {'field': 'name', 'filter': 'agTextColumnFilter', 'minWidth': 180, 'enableRowGroup': True},
        {'field': 'sex', 'filter': 'agSetColumnFilter', 'maxWidth': 80},
        {'field': 'age', 'filter': 'agNumberColumnFilter', 'maxWidth': 90},
        {'field': 'height', 'filter': 'agNumberColumnFilter', 'maxWidth': 100, 'headerName': 'Height (cm)'},
        {'field': 'weight', 'filter': 'agNumberColumnFilter', 'maxWidth': 100, 'headerName': 'Weight (kg)'},
        {'field': 'team', 'filter': 'agTextColumnFilter', 'minWidth': 140},
        {'field': 'noc', 'filter': 'agSetColumnFilter', 'maxWidth': 90,
         'enableRowGroup': True, 'headerName': 'Country'},
        {'field': 'games', 'filter': 'agSetColumnFilter', 'minWidth': 140,
         'enableRowGroup': True},
        {'field': 'year', 'filter': 'agNumberColumnFilter', 'maxWidth': 90,
         'enableRowGroup': True, 'sort': 'desc'},
        {'field': 'season', 'filter': 'agSetColumnFilter', 'maxWidth': 100,
         'enableRowGroup': True},
        {'field': 'city', 'filter': 'agSetColumnFilter', 'minWidth': 130},
        {'field': 'sport', 'filter': 'agSetColumnFilter', 'minWidth': 140,
         'enableRowGroup': True},
        {'field': 'event', 'filter': 'agTextColumnFilter', 'minWidth': 220},
        {'field': 'medal', 'filter': 'agSetColumnFilter', 'maxWidth': 110,
         'enableRowGroup': True},
    ]
    return render(request, 'demo_app/index.html', {
        'column_defs_json': json.dumps(column_defs),
        'ag_grid_license_key': getattr(settings, 'AG_GRID_LICENSE_KEY', ''),
    })


@csrf_exempt
@require_POST
def athletes_ssrm(request):
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON')
    ssrm_req = SSRMRequest.from_body(body)
    config = _build_config()
    result = process_ssrm_request(config, ssrm_req, AthleteEvent.objects.all())
    return JsonResponse(result)


@require_GET
def athletes_column_values(request):
    col_id = request.GET.get('column', '')
    if not col_id:
        return HttpResponseBadRequest("Missing 'column' query parameter")
    try:
        limit = int(request.GET.get('limit', 500))
    except ValueError:
        return HttpResponseBadRequest("Invalid 'limit'")
    config = _build_config()
    values = get_distinct_values(
        AthleteEvent.objects.all(), col_id, config.get_fields_dict(), limit=limit,
    )
    return JsonResponse({'values': values})
