# Demo project

A minimal Django project that serves the **120 Years of Olympic History**
public dataset (271,116 athlete-event records, Athens 1896 – Rio 2016)
through AG Grid Server-Side Row Model, powered by `django-aggrid-ssrm`.

The dataset is shipped gzipped at [`data/olympics.csv.gz`](data/olympics.csv.gz)
(~5 MB compressed). It comes from
[TidyTuesday 2024-08-06](https://github.com/rfordatascience/tidytuesday/tree/main/data/2024/2024-08-06),
originally compiled by Randi H. Griffin on Kaggle.

## Run it

```powershell
uv sync --extra demo
uv run python demo/manage.py migrate
uv run python demo/manage.py seed_demo            # all 271,116 rows (~30s)
uv run python demo/manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

For a faster boot while iterating, seed a smaller slice:

```powershell
uv run python demo/manage.py seed_demo --limit 20000
```

To wipe and re-seed:

```powershell
uv run python demo/manage.py seed_demo --clear --limit 50000
```

## What to try

- **Sort** any column header. Click `year` to flip Summer/Winter games chronology;
  click `name` for athletes alphabetically.
- **Filter** —
  - `name`, `team`, `event` get a **text** filter (icontains).
  - `noc`, `sport`, `season`, `medal`, `games`, `city` get a **set** filter
    populated from `/column-values/`.
  - `age`, `height`, `weight`, `year` get a **number** filter (incl. `inRange`).
- **Group** — drag `sport`, `noc`, `year`, `season`, or `medal` into the
  *Row Groups* panel at the top. Drill into a group to see its leaf rows.
  (Row grouping is marked experimental in the library README — verify counts
  look right for your case.)
- **Search** — type in the search box above the grid; it OR-combines an
  `icontains` across `name`, `team`, `sport`, and `event`.
- **Big block test** — set `medal` set filter to `Gold` and scroll: SSRM
  fetches 100-row blocks as you scroll, never loading the full dataset
  into the browser.

## Files of interest

- [demo_app/views.py](demo_app/views.py) — `_build_config()` declares the 14
  grid columns; the `/ssrm/` and `/column-values/` endpoints wire up to the
  library in ~15 lines each.
- [demo_app/models.py](demo_app/models.py) — the `AthleteEvent` model
  (one row per athlete × event).
- [demo_app/templates/demo_app/index.html](demo_app/templates/demo_app/index.html)
  — the AG Grid client-side bootstrap: column defs, ServerSideDatasource,
  license-key plumbing.
- [demo_app/management/commands/seed_demo.py](demo_app/management/commands/seed_demo.py)
  — streams the gzipped CSV in 5,000-row batches.

## Removing the AG Grid trial watermark

AG Grid Server-Side Row Model is an Enterprise feature. Without a license
key the grid runs in trial mode and shows a watermark — this is expected
and not a bug in the demo. Set your license key in the environment before
running the server:

```powershell
$env:AG_GRID_LICENSE_KEY = "your-key-here"
uv run python demo/manage.py runserver
```

This demo does not bundle a license key. See
<https://www.ag-grid.com/license-pricing/> for AG Grid licensing terms.
