# Operations

## Backfilling

```
manage.py panoramax_backfill
```

Recomputes federation state for every collection. Needed in three situations:

- **First install.** Signals only see writes made after the app was added, so
  an existing archive has no federation state until this runs.
- **After bulk writes.** `bulk_create` and queryset `update()` bypass Django's
  signals entirely, so anything they touched is invisible to the adapter.
- **After a settings change.** Widening `PANORAMAX_LICENSE_ALLOWLIST` changes
  what is eligible without writing to any row, so nothing fires.

Useful flags:

```
manage.py panoramax_backfill --collection 42 --collection 43
manage.py panoramax_backfill --touch
```

`--touch` bumps `updated` on every collection, forcing the next harvest to
re-crawl the whole catalogue. By default the command deliberately does *not*,
so a routine reconcile does not look like a site-wide edit.

Running it on a schedule (nightly, say) is a reasonable safety net against
missed signals.

## Ruling on individual images

```
manage.py panoramax_decide exclude --image 17 --reason "rights unclear"
manage.py panoramax_decide include --collection 42
manage.py panoramax_decide clear --collection 42
```

Add `--dry-run` to see the count without changing anything. Full detail in
[per-image control](per-image-control.md).

## Inspecting what the federation has been told

`PublishedCollection` is registered in the Django admin, read-only — every
field is derived, and editing one would only be undone by the next refresh.
Look there to answer "why is this collection not in the federation".

From a shell:

```python
from yesterdays_panoramax.models import PublishedCollection
from yesterdays_panoramax import queries

PublishedCollection.objects.filter(published=False)   # tombstones
queries.federatable_images_for(42).count()            # why is 42 empty?
```

## Withdrawing cleanly

A collection leaves the federation only when a harvester sees
`geovisio:status: "deleted"` for it. That means **removing this app, or turning
it off, does not withdraw anything** — it just stops answering, and the central
catalogue keeps what it already has.

To withdraw properly:

1. Make the collections ineligible (unpublish them, or empty the allowlist) and
   run `panoramax_backfill`. Tombstones are created.
2. Wait for at least one harvest to pick them up — the harvester runs
   frequently, but confirm rather than assume.
3. Only then remove the app.

To leave the federation entirely, also ask on the meta-catalogue issue tracker
to have the instance removed.

## Troubleshooting

**Nothing is published.** In order of likelihood: `PANORAMAX_ENABLED` is false;
`PANORAMAX_LICENSE_ALLOWLIST` is empty or its keys do not match your
`License.name` values (matching is case-insensitive but otherwise exact);
`panoramax_backfill` has not been run; the images have no georeference or no
EDTF date.

**A collection is stale in the federation.** Its `updated` did not move. Bulk
writes bypass signals — run `panoramax_backfill`. If it is stale in the
*central* catalogue but current on your instance, check that the harvester can
reach you and that the `rel="next"` chain terminates.

**Harvests stop after the first page.** Check that `links[rel="next"]` is
absolute and properly encoded. The harvester echoes it back verbatim.

**A 404 on a collection that exists.** The UUID was minted under a different
`PANORAMAX_UUID_NAMESPACE`. If the namespace was changed, every previously
published identifier is now invalid; change it back, or accept that the whole
catalogue is republished and ask for the stale entries to be dropped.

**Items appear at the wrong place.** The adapter publishes the most recently
submitted georeference, matching the site's map. If they disagree, the site's
materialized view is probably stale, not the adapter.
