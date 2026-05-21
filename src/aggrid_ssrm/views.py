"""
Optional class-based views for quickly wiring up an SSRM endpoint.

Users can subclass ``SSRMView`` and override ``get_queryset`` and
``get_config`` to expose a model via AG Grid SSRM in ~10 lines.
"""
import json

from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.views import View

from .column_values import get_distinct_values
from .engine import SSRMConfig, process_ssrm_request
from .request import SSRMRequest


class SSRMView(View):
    """
    Class-based view for an SSRM endpoint.

    Subclass and override ``get_queryset`` and ``get_config``.

    Example::

        class MyModelSSRMView(SSRMView):
            def get_queryset(self, request):
                return MyModel.objects.all()

            def get_config(self, request):
                return SSRMConfig(
                    fields=[
                        FieldDef('name', 'name', field_type='text'),
                        FieldDef('category', 'category', field_type='set'),
                        FieldDef('amount', 'amount', field_type='number'),
                    ],
                    search_fields=['name', 'category'],
                )

    Wire up with::

        path('my-model/ssrm/', MyModelSSRMView.as_view(), name='my-model-ssrm'),
    """

    def get_queryset(self, request: HttpRequest):
        raise NotImplementedError("Subclasses must implement get_queryset()")

    def get_config(self, request: HttpRequest) -> SSRMConfig:
        raise NotImplementedError("Subclasses must implement get_config()")

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        try:
            body = json.loads(request.body or b'{}')
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON body")

        ssrm_req = SSRMRequest.from_body(body)
        config = self.get_config(request)
        queryset = self.get_queryset(request)
        result = process_ssrm_request(config, ssrm_req, queryset)
        return JsonResponse(result)


class SSRMColumnValuesView(View):
    """
    Companion view that returns distinct values for an AG Grid Set Filter.

    Subclass and override ``get_queryset`` and ``get_config`` the same way
    as ``SSRMView``.  Reads the column name from the ``?column=`` query
    parameter and an optional ``?limit=`` (default 500).

    Example URL: ``GET /my-model/column-values/?column=category&limit=100``
    """

    def get_queryset(self, request: HttpRequest):
        raise NotImplementedError("Subclasses must implement get_queryset()")

    def get_config(self, request: HttpRequest) -> SSRMConfig:
        raise NotImplementedError("Subclasses must implement get_config()")

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        col_id = request.GET.get('column', '')
        if not col_id:
            return HttpResponseBadRequest("Missing 'column' query parameter")
        try:
            limit = int(request.GET.get('limit', 500))
        except ValueError:
            return HttpResponseBadRequest("Invalid 'limit' query parameter")

        config = self.get_config(request)
        queryset = self.get_queryset(request)
        values = get_distinct_values(
            queryset, col_id, config.get_fields_dict(), limit=limit,
        )
        return JsonResponse({'values': values})
