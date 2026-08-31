# Contributing

## Getting set up

The suite needs a PostGIS database — the adapter aggregates spatial extents,
filters with spatial lookups and builds vector tiles with `ST_AsMVT`, none of
which work without it.

```
docker run -d --name panoramax-pg -p 5432:5432 \
    -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=panoramax_test \
    postgis/postgis:16-3.4

pip install -e ".[test]"
./manage.py test tests
```

Connection details come from the usual `PG*` environment variables; the
defaults match the container above.

You do **not** need a Yesterdays deployment. `tests/images/` is a stub host app
reproducing the models the adapter reads.

## The stub is part of the contract

`tests/images/` is the executable statement of what this package requires from
Yesterdays — see [docs/host-contract.md](docs/host-contract.md). If upstream
changes a field the adapter reads, update the stub first, watch the suite go
red, then fix the adapter. A change that only touches the stub to make tests
pass is a change that has hidden a real incompatibility.

## Things worth knowing before changing code

- **Identifiers are permanent.** `ids.py` derives published UUIDs from
  `PANORAMAX_UUID_NAMESPACE` and the primary key. Any change to the layout
  orphans everything the federation has harvested, and is a major version.
- **Tombstones are not optional.** A collection that merely disappears from the
  feed stays in the central catalogue forever. If you touch eligibility, check
  that withdrawal still produces `geovisio:status: "deleted"`.
- **`updated` must move on any change beneath a collection.** The harvester
  filters on it. If it does not move, the change never reaches the federation.
- **The filter parser fails open.** An unrecognised clause widens the result
  set rather than rejecting the request; keep it that way, or a future
  harvester change drops this instance out of the federation.
- **`tiles.py` duplicates the eligibility rules in SQL**, because a tile has to
  be one round trip. If you change `queries.py`, change both.

## Style

`ruff check` and `ruff format`, enforced in CI. Imports at the top of the file.

## Reporting problems

Issues and pull requests:
<https://github.com/openhistorymap/yesterdays-panoramax/issues>

For problems with the federation itself — registration, harvesting, the central
catalogue — the right place is
<https://gitlab.com/panoramax/server/meta-catalog>.
