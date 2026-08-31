# How it works

## The federation is a crawler, not a protocol

There is no ActivityPub-style handshake and nothing is pushed. A central
**meta-catalogue** (`api.panoramax.xyz`, mirrored at `explore.panoramax.fr`)
runs a **harvester** that periodically crawls each registered instance's STAC
API and copies the metadata into a shared PostgreSQL database. Pictures stay on
the instance that hosts them; only catalogue entries travel.

Joining is therefore two separate things:

1. Serve an API the harvester can read — what this package does.
2. Get registered, by opening an issue on
   [`panoramax/server/meta-catalog`](https://gitlab.com/panoramax/server/meta-catalog).
   An administrator runs `stac-harvester add-instance <name> --url <url>`.
   There is no self-service endpoint.

## The contract

Everything below was read off the harvester's source
(`harvester/harvester/harvest.py`) and the catalogue's schema
(`migrations/sql/`), not from prose documentation — the harvester reads our
JSON, and the docs understate what it requires.

The harvester makes exactly four kinds of request:

| Request | When |
| --- | --- |
| `GET /api/configuration` | Once a day. |
| `GET /api/collections` | The first harvest of an instance. |
| `GET /api/collections?filter=status IN ('deleted','ready') AND updated > '<iso>'` | Every subsequent harvest. |
| `GET <collection's rel=self href>/items?limit=<n>` | For every collection the filter returned. |

Listings are exhausted by following `links[rel="next"]`. Note that item URLs
are built from the collection's own `rel="self"` href, so that link must be
absolute and must support `/items` beneath it.

### Identifiers must be UUIDs

This is a hard failure, not a warning. The catalogue's schema is:

```sql
CREATE TABLE collections (
    id UUID PRIMARY KEY GENERATED ALWAYS AS ((content ->> 'id')::UUID) STORED,
    ...
);
CREATE TABLE items (
    id UUID PRIMARY KEY GENERATED ALWAYS AS ((content ->> 'id')::UUID) STORED,
    collection_id UUID NOT NULL REFERENCES collections(id)
        GENERATED ALWAYS AS ((content ->> 'collection')::UUID) STORED,
    ...
    datetime TIMESTAMPTZ NOT NULL
);
```

An instance publishing integer identifiers aborts the harvest on its first row.
Yesterdays uses integer primary keys, and this package adds no column to the
`images` tables, so identifiers are **derived**:

- an RFC 9562 **version 8** UUID (the "custom format", which is exactly this:
  an application laying out the bits itself);
- leading nine bytes: a digest of `(PANORAMAX_UUID_NAMESPACE, kind)`, with the
  version and variant bits stamped over it;
- trailing seven bytes: the primary key, big-endian.

That makes them stable, invertible without a lookup table, and rejectable when
they came from somewhere else — a UUID minted under a different namespace
decodes to nothing and yields a 404 rather than the wrong row.

See `ids.py`. The scheme supports primary keys up to 2⁵⁶−1.

### `datetime` is `NOT NULL`

Images without a parseable date cannot be published at all. See
[data mapping](data-mapping.md#dates).

### Change detection hangs off the *collection*

The incremental filter is on the **collection's** `updated`; the harvester then
re-fetches all of that collection's items. `images.Collection.updated_at` only
moves when the collection row itself is written — so a new georeference on one
of its images would never propagate, and the federation would hold a stale copy
forever.

This package therefore keeps its own `PublishedCollection.updated`, maintained
by signals and bumped by *any* change beneath the collection: a georeference
added or removed, an image edited, moved in, moved out, a source going private.

### Deletion needs a tombstone

A collection is removed from the federation only when the harvester sees
`geovisio:status: "deleted"` for it:

```python
if collection.get("geovisio:status") == "deleted":
    await _delete_collection(...)
else:
    await _import_collection(...)
```

A collection that merely stops appearing in the feed is treated as unchanged
and stays in the central catalogue indefinitely. So when a collection is made
private — or its source is, or its last eligible image goes away — this package
keeps a **tombstone** and keeps serving it, flagged deleted, to any harvester
that asks. Unfiltered listings hide tombstones; only a request naming
`status IN ('deleted', ...)` sees them.

### Which links survive

The harvester strips `self`, `collection`, `parent`, `root`, `prev`, `next` and
`related` from items, and recomputes them. It keeps everything else — which is
why each item carries a `rel="via"` link back to its page on your site. That
backlink travels into the federation.

## What we do with the filter

The harvester sends one expression, machine-generated and narrow. This package
parses that shape rather than implementing CQL2 (Panoramax's own server runs a
deliberately lax fork of `cql2-rs` for the same reason).

An unrecognised clause is **ignored with a warning, not rejected**, because the
two failure modes are not symmetric:

- Ignoring a clause widens the result set. The harvester does more work than it
  needed to, and still sees everything.
- Rejecting the request stops the harvest dead; silently narrowing it drops
  collections on the floor with nobody noticing.

If a future harvester sends a filter this package has never seen, the instance
degrades to full listings instead of falling out of the federation.

## Pagination

Keyset, not offset, throughout. The harvester walks an entire catalogue while
it is being written to, and offsets skip or repeat rows when something is
inserted mid-walk. Collections page on `(updated, collection_pk)`; items and
search page on the primary key.
