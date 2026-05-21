# django-aggrid-ssrm

A Django backend adapter for [AG Grid's Server-Side Row Model (SSRM)](https://www.ag-grid.com/javascript-data-grid/server-side-model/).
Translate `filterModel`, `sortModel`, pagination, search, and grouping
requests from AG Grid Enterprise into Django ORM operations with a few
lines of `FieldDef` config.

---

## ⚠ Important — License notice

**AG Grid's Server-Side Row Model is an [AG Grid Enterprise](https://www.ag-grid.com/license-pricing/) feature.**
You must hold a valid AG Grid Enterprise license to use SSRM in production.
Without one, the grid still works but shows a trial watermark.

- AG Grid Licensing: <https://www.ag-grid.com/license-pricing/>
- AG Grid Enterprise EULA: <https://www.ag-grid.com/eula/AG-Grid-Enterprise-License-Latest.pdf>

**This Django library is independent of AG Grid Ltd.** It is released under
the **MIT License** (see [LICENSE](LICENSE)) — free and open source. It
implements the *server-side* of the SSRM protocol only; it does not bundle
or redistribute the AG Grid JavaScript library itself.

---

## Install

```powershell
uv add django-aggrid-ssrm
```

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'aggrid_ssrm',
]
```

That's it — there are no models or migrations to apply.

## Quick start

A complete SSRM endpoint in ~20 lines:

```python
# views.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from aggrid_ssrm import FieldDef, SSRMConfig, SSRMRequest, process_ssrm_request
from .models import AthleteEvent

CONFIG = SSRMConfig(
    fields=[
        FieldDef('name',   'name',   field_type='text'),
        FieldDef('noc',    'noc',    field_type='set'),     # country code
        FieldDef('year',   'year',   field_type='number'),
        FieldDef('sport',  'sport',  field_type='set'),
        FieldDef('medal',  'medal',  field_type='set'),
    ],
    default_sort=['-year', 'name'],
    search_fields=['name', 'team', 'sport', 'event'],
)

@csrf_exempt
def athletes_ssrm(request):
    body = json.loads(request.body or b'{}')
    req = SSRMRequest.from_body(body)
    result = process_ssrm_request(CONFIG, req, AthleteEvent.objects.all())
    return JsonResponse(result)   # {"rowData": [...], "rowCount": N}
```

```python
# urls.py
urlpatterns = [
    path('athletes/ssrm/', athletes_ssrm),
]
```

Wire AG Grid's `ServerSideDatasource` to `POST /athletes/ssrm/` and you're done.
A full runnable example with this exact model lives in [`demo/`](demo/).

## Status / feature coverage

| Feature | Status |
| --- | --- |
| Filtering — text, number, date, set, blank/notBlank, combined AND/OR | **Stable** — extensive test coverage |
| Sorting — multi-column asc/desc | **Stable** |
| Pagination — block loading via `startRow`/`endRow`, virtual `lastRowIndex` | **Stable** |
| Distinct values for Set Filter dropdowns | **Stable** |
| Free-text search across direct + JSON-array fields | **Stable** |
| Row expansion (one DB row → N grid rows via `row_expander`) | **Stable** |
| **Row grouping & aggregation** (`rowGroupCols`, `groupKeys`, `valueCols`) | ⚠ **Experimental** — see caveat below |
| Pivoting (`pivotMode`, `pivotCols`) | ❌ Not implemented |

### Grouping caveat

Row grouping works for many common cases and has test coverage, but is
treated as an **extra / non-primary feature** of this library. It depends
on the shape of your data — especially when grouping by fields inside a
`JSONField`, where it falls back to Python-level aggregation or raw-SQL
`json_each` (SQLite-flavoured). In particular:

- Multi-level grouping over JSON-array-nested fields may not match every
  use case; verify the row counts you get back match what you expect.
- The `json_array_config` path uses raw SQL keyed off SQLite's
  `json_each` / `json_extract`. PostgreSQL works for non-array paths,
  but the array-nested branch is currently SQLite-shaped.
- Aggregation aliases that collide with reserved row keys
  (e.g. `childCount`) will be filtered out — known limitation.

If grouping doesn't fit your case, you can disable it per-column via
`FieldDef(..., groupable=False)`, or just don't enable
`enableRowGroup` on the column definitions.

If you hit a grouping case that misbehaves, please open an issue with the
request payload and expected vs. actual output.

## Concepts

### `FieldDef`

One per AG Grid column. Tells the engine the ORM path and what filter
operators are valid.

```python
FieldDef(
    col_id='region',          # AG Grid colId
    orm_path='region',        # Django ORM lookup path
    field_type='set',         # 'text' | 'number' | 'date' | 'set'
    sortable=True,            # default True
    filterable=True,          # default True
    groupable=True,           # default True
    value_getter=None,        # optional callable(instance) -> value
    is_json=False,            # set True for fields inside a JSONField
    json_array_config=None,   # for arrays nested in JSONFields
)
```

### `SSRMConfig`

Per-endpoint configuration: fields, default sort, search fields, row
builder, max page size.

### Request flow

```
AG Grid → POST {filterModel, sortModel, startRow, endRow, rowGroupCols, ...}
                                  ↓
                       SSRMRequest.from_body(body)
                                  ↓
              process_ssrm_request(config, req, queryset)
                                  ↓
                     apply search → apply filters
                                  ↓
                grouped?  ──yes──→ handle_grouped_request
                   no
                   ↓
                sort → paginate → row_builder
                                  ↓
                       {"rowData": [...], "rowCount": N}
```

## Filter type reference

| AG Grid filter | Operator | Django lookup |
| --- | --- | --- |
| text | `contains`           | `__icontains` |
| text | `notContains`        | `~Q(__icontains)` |
| text | `equals`             | `__iexact` |
| text | `notEqual`           | `~Q(__iexact)` |
| text | `startsWith`         | `__istartswith` |
| text | `endsWith`           | `__iendswith` |
| text | `blank` / `notBlank` | `__isnull` + `= ''` |
| number | `equals`           | exact |
| number | `greaterThan(OrEqual)` | `__gt` / `__gte` |
| number | `lessThan(OrEqual)`   | `__lt` / `__lte` |
| number | `inRange`             | `__gte` & `__lte` |
| number | `blank` / `notBlank`  | `__isnull` |
| date   | `equals`              | `__date` |
| date   | `greaterThan`         | `__date__gt` |
| date   | `lessThan`            | `__date__lt` |
| date   | `inRange`             | `__date__gte` & `__date__lte` |
| set    | `values: [...]`       | `__in` |
| combined | `AND` / `OR`        | `Q(...) & Q(...)` / `Q(...) | Q(...)` |

## Class-based view helper

If you'd rather not write the JSON-decoding boilerplate yourself:

```python
from aggrid_ssrm.views import SSRMView, SSRMColumnValuesView

class AthleteSSRMView(SSRMView):
    def get_queryset(self, request):
        return AthleteEvent.objects.all()
    def get_config(self, request):
        return CONFIG

class AthleteColumnValuesView(SSRMColumnValuesView):
    def get_queryset(self, request):
        return AthleteEvent.objects.all()
    def get_config(self, request):
        return CONFIG
```

## Demo

A runnable Django project with an `AthleteEvent` model and the public
[120 Years of Olympic History dataset](https://github.com/rfordatascience/tidytuesday/tree/main/data/2024/2024-08-06)
(271,116 rows, Athens 1896 – Rio 2016) lives in [`demo/`](demo/):

```powershell
uv sync --extra demo
uv run python demo/manage.py migrate
uv run python demo/manage.py seed_demo            # all 271k rows; use --limit N for a smaller slice
uv run python demo/manage.py runserver
```

Open <http://127.0.0.1:8000/>. AG Grid Enterprise loads from a CDN; expect
the trial watermark unless you set `AG_GRID_LICENSE_KEY` in the
environment. See [`demo/README.md`](demo/README.md) for the full walkthrough.

## Development

```powershell
uv sync --extra dev
uv run pytest
```

271 tests covering filters, sorting, grouping, pagination, row expansion,
distinct values, JSON arrays, and edge cases.

## License

This library: **MIT** — see [LICENSE](LICENSE). © 2026 Zpatel.

AG Grid Enterprise (a separate product you need at runtime to use SSRM in
the browser): see <https://www.ag-grid.com/license-pricing/> for terms.
This library does not redistribute AG Grid.
