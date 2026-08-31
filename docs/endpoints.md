# Endpoints

All paths are relative to the `/api/` mount point, which is
[not negotiable](how-it-works.md#the-contract).

| Path | Description |
| --- | --- |
| `GET /api/` | STAC catalogue root: `conformsTo` and discovery links |
| `GET /api/configuration` | Instance identity, licence, contact |
| `GET /api/collections` | Collection listing |
| `GET /api/collections/queryables` | Filterable properties (`created`, `updated`) |
| `GET /api/collections/{uuid}` | One collection |
| `GET /api/collections/{uuid}/items` | Its items |
| `GET /api/collections/{uuid}/items/{uuid}` | One item |
| `GET /api/collections/{uuid}/thumb.jpg` | Collection preview (redirect) |
| `GET /api/pictures/{uuid}/thumb.jpg` | Item preview (redirect) |
| `GET /api/search` | STAC item search |
| `GET /api/map/style.json` | MapLibre style |
| `GET /api/map/{z}/{x}/{y}.mvt` | Vector tiles |

Everything is read-only and unauthenticated. There is no upload API: Yesterdays
is an archive of scanned photographs, not a capture target, so
`/api/configuration` advertises no registration and no upload.

## `/api/collections`

| Parameter | Meaning |
| --- | --- |
| `limit` | Page size, clamped to `PANORAMAX_MAX_PAGE_SIZE` |
| `filter` | CQL2 subset: `status IN (...)` and `updated`/`created` comparisons |
| `page` | Opaque keyset cursor; follow `links[rel="next"]` instead |

Tombstones (withdrawn collections, `geovisio:status: "deleted"`) appear only
when the filter names `status IN ('deleted', ...)`. An unfiltered listing shows
the live catalogue.

## `/api/search`

| Parameter | Meaning |
| --- | --- |
| `bbox` | `west,south,east,north` in WGS 84 |
| `datetime` | An instant or `start/end`; **year-granular**, `..` for open bounds |
| `collections` | Comma-separated collection UUIDs |
| `ids` | Comma-separated item UUIDs |
| `limit`, `page` | As above |

Returns a GeoJSON `FeatureCollection`.

## Vector tiles

Three layers, switched by zoom, matching Panoramax's own breakpoints so a
viewer configured for the federation behaves the same against your instance:

| Layer | Zoom | Properties |
| --- | --- | --- |
| `grid` | < 6 | `id`, `nb_pictures`, `coef` |
| `sequences` | < 15 | `id`, `nb_pictures` |
| `pictures` | ≥ 15 | `id`, `ts`, `heading` |

`id` is the federated UUID, not the primary key, because the viewer uses it to
fetch the item straight back out of the API.

The landing page advertises the tiles as `rel="xyz"` and the style as
`rel="xyz-style"`, which is how the Panoramax viewer discovers a third-party
instance.

## Pagination

Keyset, not offset. Follow `links[rel="next"]` and do not construct cursors by
hand — the format is not part of the API's contract and may change.
