# Data mapping

## What gets published

An image is published only if **all** of these hold:

- its collection and source are public, and it is not marked a duplicate —
  this is the existing `Image.is_searchable` flag, so the adapter agrees with
  the rest of the site by construction;
- it has at least one georeference;
- it has a parseable EDTF date (the catalogue's `datetime` column is
  `NOT NULL`);
- its licence is in `PANORAMAX_LICENSE_ALLOWLIST`;
- it is not an aerial, and not flagged `will_not_georef`;
- it has a `permalink`.

A `Collection` with at least one such image becomes a STAC Collection; each
eligible `Image` becomes a STAC Item.

## Which georeference wins

An image can carry many georeferences — several contributors, later
corrections, differing confidence — but a STAC item has one geometry and one
azimuth.

**The most recently submitted georeference wins.** That is the same rule the
rest of the site already applies: it is what the `public_georeferences_mvt`
materialized view encodes for the map tiles and the GeoJSON endpoints.
Publishing a different point from the one the site itself displays would be a
bug that is very hard to see.

The adapter reads it through the ORM rather than from that view, because the
view is refreshed asynchronously and lacks the columns the eligibility rules
need. The *rule* is shared; the plumbing is not.

## Dates

Yesterdays stores [EDTF](https://www.loc.gov/standards/datetime/), which is
frequently a range: `1890`, `189X`, `1901-06`. STAC's answer is the
datetime-range form from the common metadata spec:

- `start_datetime` and `end_datetime` describe the range;
- `datetime` is pinned to the **start**.

The start, not the midpoint. A midpoint is a value no source ever asserted and
it drifts as soon as the range is widened; the start is the earliest moment the
photograph could have been taken, which is a claim the archive actually makes.

The original EDTF string is published verbatim as `yesterdays:edtf`, because no
STAC field carries its qualifiers.

Temporal *search* (`?datetime=`) is **year-granular**: an image's interval only
exists once EDTF has been parsed in Python, and the database only holds the
bounding years (`start_decdate` / `end_decdate`).

Historical dates are not a problem for the federation in practice — the OSM-FR
instance already carries items back to 1904.

## Position accuracy

`Georeference.confidence` (low/medium/high) is published as
`quality:horizontal_accuracy` in metres, via `PANORAMAX_CONFIDENCE_ACCURACY_M`,
alongside `yesterdays:confidence` carrying the original label.

There is no measured conversion between the two. The defaults are deliberately
pessimistic order-of-magnitude estimates, published so that a consumer can tell
a crowd-placed historical photograph from a GPS track rather than being
silently misled about precision.

## Assets

| STAC asset | Role | Source |
| --- | --- | --- |
| `hd` | `data` | `Image.display_permalink` (transform applied) |
| `sd` | `visual` | the same full-size asset |
| `thumb` | `thumbnail` | `Image.thumbnail` (500px longest side) |

Panoramax's `sd` is normally a fixed 2048px-wide rendition. Yesterdays
generates no intermediate size — only a full-size transformed image and a 500px
thumbnail — so `sd` points at the full-size asset. Serving something larger
than advertised costs bandwidth; omitting the `visual` role breaks viewers
outright.

`hd` is `display_permalink`, meaning the *transformed* rendition, with any
rotation or mirror already baked in. Consequently
`pers:interior_orientation.sensor_array_dimensions` describes the asset that is
actually served: a 90° or 270° rotation swaps the stored width and height.

No `field_of_view` is emitted. These are flat photographs, and the
meta-catalogue keys off `field_of_view == 360` to file a picture as
equirectangular:

```sql
CASE WHEN content #>> '{properties,pers:interior_orientation,field_of_view}' = '360'
     THEN 'equirectangular' ELSE 'flat' END
```

## Collection licences

A collection carries the SPDX id shared by all of its published images, or
`other` when they differ. It is denormalized onto `PublishedCollection` so that
listing a page of collections does not need a distinct-licence query per
collection.

## Ordering

Items are ordered by primary key. Chronological order would read better, but an
archival collection's dates are EDTF strings whose only sortable projection in
the database is the year — so it would be neither a true chronology nor a
unique key, and a keyset cursor needs a unique key.

## The `sequences` vector layer

Panoramax draws `sequences` as lines, because one of its sequences is a walk or
a drive with pictures along a path. A Yesterdays collection is an archival album
— photographs scattered across a city over decades, in no spatial order at all
— so joining them into a line would draw a route nobody ever walked.

This package publishes each collection as a **multipoint**, and the
`style.json` it serves draws it as points. The central catalogue builds its own
geometry from the harvested items regardless, so the choice only affects
viewers pointed straight at your instance.
