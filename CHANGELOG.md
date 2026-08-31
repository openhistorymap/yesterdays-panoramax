# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows semantic versioning — with one project-specific rule: **any change to
the identifier scheme is a major version**, because published UUIDs are a
function of it and changing them orphans everything already harvested.

## [Unreleased]

### Added

- Per-image federation control. `ImageDecision` records an explicit ruling to
  include or exclude one image, for judgements the licence and visibility rules
  cannot express. Rows exist only for images somebody has ruled on, so the
  feature is inert until used.
- `PANORAMAX_IMAGE_POLICY`, either `"opt-out"` (the default: publish everything
  eligible minus exclusions) or `"opt-in"` (publish nothing until approved, for
  archives whose rights are settled picture by picture). An unrecognised value
  raises rather than falling back to publishing.
- `yesterdays_panoramax.api` — `exclude_image`, `include_image`,
  `clear_decision`, `decision_for`, `is_published` — a stable surface for the
  host to drive the control from its own views and admin actions.
- `panoramax_decide` management command for ruling on images in bulk, by id or
  by collection, with `--dry-run`.
- Editable Django admin for `ImageDecision`, recording who decided and why.
- CI now runs `makemigrations --check`, since this package's migrations are
  written by hand and drift would surface as a phantom migration downstream.

### Notes

- An exclusion is absolute; an approval is not an override. An approved image
  still has to satisfy the licence, visibility, date and georeference rules.

## [0.1.0] — 2026-08-31

First release. Extracted from the Yesterdays repository into a standalone,
installable Django app.

### Added

- A Panoramax-compatible STAC API served under `/api/`: catalogue root,
  `/configuration`, `/collections` (with the harvester's CQL2 subset and keyset
  pagination), `/collections/{uuid}/items`, single item and collection
  endpoints, `/search`, thumbnail redirects, `style.json` and vector tiles.
- Derived RFC 9562 version-8 identifiers, so integer primary keys can be
  published into the meta-catalogue's UUID columns without adding a column to
  the `images` tables.
- `PublishedCollection`, tracking per-collection federation state: change
  detection for incremental harvests, and tombstones so withdrawn collections
  are actually removed from the federation rather than silently abandoned.
- Signals maintaining that state from `images` writes, batched per transaction
  and deferred to commit.
- `panoramax_backfill` management command, for first install, bulk writes and
  settings changes.
- Read-only Django admin for inspecting federation state.
- Licence allowlist acting as both the publication gate and the SPDX
  translation, empty by default.
- Vector tiles with `grid`, `sequences` and `pictures` layers at Panoramax's
  own zoom breakpoints.

[Unreleased]: https://github.com/openhistorymap/yesterdays-panoramax/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/openhistorymap/yesterdays-panoramax/releases/tag/v0.1.0
