# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows semantic versioning — with one project-specific rule: **any change to
the identifier scheme is a major version**, because published UUIDs are a
function of it and changing them orphans everything already harvested.

## [Unreleased]

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
