# yesterdays-panoramax

[![CI](https://github.com/openhistorymap/yesterdays-panoramax/actions/workflows/ci.yml/badge.svg)](https://github.com/openhistorymap/yesterdays-panoramax/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/yesterdays-panoramax.svg)](https://pypi.org/project/yesterdays-panoramax/)
[![Python](https://img.shields.io/pypi/pyversions/yesterdays-panoramax.svg)](https://pypi.org/project/yesterdays-panoramax/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)

A Django app that publishes a [Yesterdays](https://github.com/maprva/yesterdays)
historical image archive to the [Panoramax](https://panoramax.fr/) federation,
by serving a Panoramax-compatible [STAC](https://stacspec.org/) API.

Drop it into an existing installation: one dependency, one line in
`INSTALLED_APPS`, one URL include, one migration. It adds no column to the
`images` tables and changes no existing behaviour.

```
pip install yesterdays-panoramax
```

## What it does

Panoramax is not a push protocol. A central **meta-catalogue**
(`api.panoramax.xyz`) runs a **harvester** that crawls each registered
instance's STAC API on a schedule and copies the *metadata* into a shared,
searchable database. The pictures never move — they stay on the instance that
hosts them.

This package makes a Yesterdays instance one of those crawlable instances. Your
georeferenced historical photographs become discoverable alongside the rest of
the federation, and every item links back to its record on your site.

It maps:

| Yesterdays | Panoramax / STAC |
| --- | --- |
| `images.Collection` | STAC Collection ("sequence") |
| `images.Image` | STAC Item ("picture") |
| latest `Georeference.point` | item geometry |
| `Georeference.direction` | `view:azimuth` |
| `Georeference.confidence` | `quality:horizontal_accuracy` |
| `Image.edtf_date` | `datetime` + `start_datetime`/`end_datetime` |
| `display_permalink` / `thumbnail` | `hd` / `sd` / `thumb` assets |

## Quick start

```python
# settings.py
INSTALLED_APPS = [
    ...,
    "yesterdays_panoramax",
]

PANORAMAX_ENABLED = True

# images.License names -> SPDX identifiers.
PANORAMAX_LICENSE_ALLOWLIST = {
    "No known copyright restrictions": "CC0-1.0",
    "CC BY-SA 4.0": "CC-BY-SA-4.0",
}

PANORAMAX_INSTANCE_NAME = "Yesterdays"
PANORAMAX_CONTACT_EMAIL = "you@example.org"

# Set once. Never change it. See docs/configuration.md.
PANORAMAX_UUID_NAMESPACE = "6f3d6b1a-6b0e-5a3f-9c8d-0f1c2a4b8e7d"
```

```python
# urls.py -- the /api/ prefix is not optional, see below
urlpatterns = [
    ...,
    path("api/", include("yesterdays_panoramax.urls", namespace="panoramax")),
]
```

```
manage.py migrate panoramax
manage.py panoramax_backfill
```

> [!IMPORTANT]
> The harvester builds its requests as `{instance_url}/api/collections` with
> the prefix **hardcoded**, so the app must be mounted at `/api/`. If your
> project already serves something there — Yesterdays serves its REST API at
> `/api/v2/` — include this app *after* those routes.

Publication is opt-in twice over: `PANORAMAX_ENABLED`, and a licence allowlist
that starts empty. An instance with the flag on and no allowlist publishes
nothing. That is deliberate — Panoramax's federation policy expects open
licensing, and only a human can say which of an archive's licences qualify.

## Joining the federation

Serving the API is only half of it. To actually be harvested, open an issue on
[`panoramax/server/meta-catalog`](https://gitlab.com/panoramax/server/meta-catalog)
asking to be added; an administrator runs
`stac-harvester add-instance <name> --url https://your.instance`. There is no
self-service endpoint.

Before you do, two questions the code cannot answer for you:

- **Licensing.** The federation expects Licence Ouverte 2.0 or CC-BY-SA 4.0,
  and `/api/configuration` advertises one instance-wide licence.
- **Fit.** Panoramax catalogues contemporary field photography for
  OpenStreetMap mapping. Historical photographs with crowd-estimated positions
  are a different kind of data. There is precedent — the OSM-FR instance
  carries items back to 1904 — but it is worth raising with the Panoramax
  community *before* publishing at scale.

## Documentation

| | |
| --- | --- |
| [Installation](docs/installation.md) | Adding it to a Yesterdays project |
| [Configuration](docs/configuration.md) | Every setting, and what it does |
| [How it works](docs/how-it-works.md) | The federation model and the harvester contract |
| [Data mapping](docs/data-mapping.md) | What gets published, and the judgement calls |
| [Endpoints](docs/endpoints.md) | The API surface |
| [Operations](docs/operations.md) | Backfilling, withdrawal, troubleshooting |
| [Host contract](docs/host-contract.md) | What the package needs from `images` |
| [Releasing](docs/releasing.md) | Cutting a version |

## Requirements

- Python 3.11+
- Django 4.2+
- PostgreSQL with PostGIS (the adapter aggregates extents, filters spatially,
  and builds vector tiles with `ST_AsMVT`)
- A Yesterdays installation providing the `images` app — see
  [host contract](docs/host-contract.md)

## Development

```
pip install -e ".[test]"
./manage.py test tests
```

The suite runs against a stubbed host app in `tests/images/`, so you do not
need a full Yesterdays deployment. It needs a PostGIS database; connection
details come from the usual `PG*` environment variables.

## Licence

AGPL-3.0-or-later, matching Yesterdays. See [LICENSE](LICENSE).
