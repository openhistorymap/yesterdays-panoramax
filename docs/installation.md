# Installation

## Requirements

- Python 3.11+
- Django 4.2+
- PostgreSQL with PostGIS. The adapter aggregates spatial extents, filters with
  spatial lookups, and builds vector tiles with `ST_AsMVT`; none of that works
  on SQLite or on Postgres without PostGIS.
- A Yesterdays installation providing the `images` app. See the
  [host contract](host-contract.md) for exactly which models and fields are
  required.

## Install

```
pip install yesterdays-panoramax
```

Or, with `uv`, add it to `pyproject.toml`:

```toml
dependencies = [
    ...,
    "yesterdays-panoramax>=0.1",
]
```

## Wire it up

**1. Add the app.** It must come after `images`, and after
`django.contrib.gis`:

```python
INSTALLED_APPS = [
    ...,
    "django.contrib.gis",
    "images",
    "yesterdays_panoramax",
]
```

The importable name is `yesterdays_panoramax`; the Django app *label* is
`panoramax`. That is pinned deliberately — the label decides the table name
(`panoramax_publishedcollection`) and the URL namespace
(`reverse("panoramax:...")`), and letting it follow the distribution name would
rename the table under any installation that already had one.

**2. Mount the URLs at `/api/`.**

```python
urlpatterns = [
    ...,
    path("api/v2/", include("api.urls")),      # Yesterdays' own REST API
    path("api/", include("yesterdays_panoramax.urls", namespace="panoramax")),
]
```

!!! danger "The prefix is not a choice"
    The meta-catalogue's harvester builds its requests as
    `{instance_url}/api/collections` and `{instance_url}/api/configuration`
    with the path hardcoded. Mounted anywhere else, the instance cannot be
    harvested. Include this app *after* any existing `api/` routes so they keep
    matching first.

**3. Migrate.**

```
manage.py migrate panoramax
```

One table, `panoramax_publishedcollection`. Nothing in `images` is altered.

**4. Configure and backfill.** See [configuration](configuration.md), then:

```
manage.py panoramax_backfill
```

Signals only observe writes made *after* the app is installed, so an existing
archive has no federation state until this runs.

## Verifying

```
curl -s https://your.instance/api | jq .conformsTo
curl -s https://your.instance/api/configuration | jq .name
curl -s "https://your.instance/api/collections?limit=1" | jq '.collections[0].id'
```

The third should print a UUID. If it prints `null`, nothing is eligible yet —
check `PANORAMAX_LICENSE_ALLOWLIST` and see [operations](operations.md).

## Removing it

The adapter is inert when `PANORAMAX_ENABLED` is false: the endpoints still
answer, with an empty catalogue. To remove it entirely, first let a harvest see
every collection withdrawn (so the federation drops them), then
`manage.py migrate panoramax zero` and drop the app. Uninstalling without that
step leaves your collections in the central catalogue indefinitely — see
[operations](operations.md#withdrawing-cleanly).
