# Demo project

A minimal Django project that serves AG Grid Server-Side Row Model from a
`Sale` model, demonstrating `django-aggrid-ssrm`.

## Run it

```powershell
uv sync --extra demo
uv run python demo/manage.py migrate
uv run python demo/manage.py seed_demo --count 5000
uv run python demo/manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

## What to try

- **Sort** any column header.
- **Filter** — text columns get a text filter, `region`/`category` get a set
  filter populated from `/column-values/`, numeric columns get a number filter,
  `sold_at` gets a date filter.
- **Group** — drag `region` or `category` into the *Row Groups* panel at the
  top. Drill into a group to see its leaf rows.
- **Search** — type in the search box above the grid; it OR-combines an
  `icontains` across `product`, `sales_rep`, and `region`.

## Files of interest

- [demo_app/views.py](demo_app/views.py) — the `_build_config()` function shows
  how to declare grid columns, and how the `/ssrm/` and `/column-values/`
  endpoints wire up to the library.
- [demo_app/templates/demo_app/index.html](demo_app/templates/demo_app/index.html)
  — the AG Grid client-side bootstrap: column defs, ServerSideDatasource,
  license-key plumbing.
- [demo_app/management/commands/seed_demo.py](demo_app/management/commands/seed_demo.py)
  — the fixture generator.

## Removing the AG Grid trial watermark

Set your license key in the environment before running the server:

```powershell
$env:AG_GRID_LICENSE_KEY = "your-key-here"
uv run python demo/manage.py runserver
```

This demo does not bundle a license key; the watermark is expected if you
have not set one. See <https://www.ag-grid.com/license-pricing/>.
