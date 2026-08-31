# yesterdays-panoramax

Publishes a [Yesterdays](https://github.com/maprva/yesterdays) historical image
archive to the [Panoramax](https://panoramax.fr/) federation.

## Contents

- **[Installation](installation.md)** — adding the app to a project
- **[Configuration](configuration.md)** — every setting
- **[How it works](how-it-works.md)** — the federation model, and the exact
  contract the harvester imposes
- **[Data mapping](data-mapping.md)** — what is published, and the judgement
  calls behind it
- **[Endpoints](endpoints.md)** — the API surface
- **[Operations](operations.md)** — backfilling, withdrawal, troubleshooting
- **[Host contract](host-contract.md)** — what this package needs from `images`
- **[Releasing](releasing.md)** — cutting a version

## In one paragraph

Panoramax federates by *pull*: a central meta-catalogue crawls each registered
instance's STAC API and copies the metadata, leaving the pictures where they
are. This package turns a Yesterdays instance into one of those crawlable
instances — mapping collections to STAC Collections and georeferenced images to
STAC Items, tracking what has changed so incremental harvests work, and
tombstoning anything withdrawn so the federation is told to drop it. It is
self-contained: no column is added to the `images` tables, and no existing
behaviour changes.
