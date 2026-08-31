# Host contract

This package is a plugin for the Yesterdays application, not a standalone
service. It reads models from an installed app whose Django label is `images`.

`tests/images/` in this repository is a stub reproducing exactly that contract —
it is not shipped, but it is the executable statement of what is required. If a
change to Yesterdays breaks the adapter, update the stub first and watch the
suite go red.

## Models and fields

### `images.Source`

`name`, `slug`, `url`, `public`

### `images.Collection`

`source` (FK), `name`, `slug`, `description`, `public`, `created_at`,
`updated_at`, `get_absolute_url()`

### `images.License`

`name` — free text; the key `PANORAMAX_LICENSE_ALLOWLIST` matches on.

### `images.Image`

| Field | Used for |
| --- | --- |
| `collection` (FK) | grouping into STAC Collections |
| `title`, `description`, `creator` | item properties |
| `permalink`, `transformed_permalink`, `thumbnail` | assets |
| `display_permalink` (property) | the `hd`/`sd` asset |
| `license` (FK, nullable) | eligibility and SPDX id |
| `edtf_date` | `datetime`, `start_datetime`, `end_datetime` |
| `start_decdate`, `end_decdate` | year-granular temporal search |
| `width`, `height`, `rotation` | `pers:interior_orientation` |
| `aerial`, `will_not_georef`, `duplicate_of` | eligibility |
| `is_searchable` | eligibility (public collection ∧ public source ∧ not duplicate) |
| `created_at`, `updated_at` | item `created` / `updated` |
| `get_absolute_url()` | the `rel="via"` backlink |

### `images.Georeference`

`image` (FK, `related_name="georeferences"`), `point` (PointField, SRID 4326),
`direction`, `confidence`, `georeferenced_at`, `updated_at`

## Behaviours relied upon

- **`is_searchable` is maintained by the host.** The adapter reads it rather
  than recomputing visibility. The host must keep it in step via `update()`
  (which fires no further signal) on image, collection and source saves.
- **`Image.save()` derives `start_decdate` / `end_decdate`** from `edtf_date`
  as the bounding years.
- **`display_permalink`** returns the transformed rendition when one exists,
  otherwise the original.

## URL names

The adapter reverses these when linking back to the host:

- `images:image_detail`, with kwarg `image_id`
- `images:collection_detail`, with kwargs `source_slug` and `collection_slug`

## Migrations

The package's migration depends on `("images", "__first__")` rather than a
pinned migration name, so the host owns its own history.
