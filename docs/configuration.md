# Configuration

Every setting is read from `django.conf.settings` at call time, so
`override_settings` works and nothing needs a restart beyond the usual.

## Switching it on

| Setting | Default | Meaning |
| --- | --- | --- |
| `PANORAMAX_ENABLED` | `False` | Whether anything is published at all. |
| `PANORAMAX_LICENSE_ALLOWLIST` | `{}` | Which licences may be federated. |

Publication is opt-in twice. An instance with the flag on and an empty
allowlist publishes nothing, which is the intended behaviour for a
half-configured install.

### `PANORAMAX_LICENSE_ALLOWLIST`

This setting does two jobs, because both need the same list.

It is the **gate**. Yesterdays holds images under a wide range of licences,
most of which Panoramax's federation policy will not accept, so publication is
opt-in per licence rather than opt-out.

It is also the **translation**. `images.License.name` is free text chosen by
whoever entered the archive, while STAC wants an SPDX identifier — and only a
human knows that "CC BY-SA 4.0" and "Creative Commons Attribution-ShareAlike
4.0 International" are the same licence.

```python
PANORAMAX_LICENSE_ALLOWLIST = {
    "No known copyright restrictions": "CC0-1.0",
    "Public Domain": "CC0-1.0",
    "CC BY-SA 4.0": "CC-BY-SA-4.0",
}
```

Keys are matched case-insensitively against `License.name`. A plain sequence of
names is also accepted, in which case every listed licence is published under
`PANORAMAX_LICENSE_ID`.

## Per-image control

| Setting | Default |
| --- | --- |
| `PANORAMAX_IMAGE_POLICY` | `"opt-out"` |

`"opt-out"` publishes everything eligible except images explicitly excluded;
`"opt-in"` publishes nothing until an image has been explicitly approved. Both
are driven by the `ImageDecision` model and the `yesterdays_panoramax.api`
helpers — see [per-image control](per-image-control.md). An unrecognised value
raises `ImproperlyConfigured` rather than quietly falling back.

The feature is inert until used: with no decisions recorded, `opt-out` behaves
exactly as it did before the model existed.

## Identity

| Setting | Default |
| --- | --- |
| `PANORAMAX_INSTANCE_NAME` | `"Yesterdays"` |
| `PANORAMAX_DESCRIPTION` | `"Georeferenced historical photographs"` |
| `PANORAMAX_CONTACT_EMAIL` | `None` |
| `PANORAMAX_GEO_COVERAGE` | `None` |
| `PANORAMAX_LOGO` | `None` |
| `PANORAMAX_COLOR` | `"#525252"` |

These populate `/api/configuration`, which the harvester re-reads once a day
and the federation uses to label your instance.

## Licensing metadata

| Setting | Default |
| --- | --- |
| `PANORAMAX_LICENSE_ID` | `"CC-BY-SA-4.0"` |
| `PANORAMAX_LICENSE_URL` | `https://creativecommons.org/licenses/by-sa/4.0/` |

The instance-wide licence advertised in `/api/configuration`. Individual
collections and items carry their own SPDX id from the allowlist; a collection
whose images disagree is published as `other`.

## Identifiers

| Setting | Default |
| --- | --- |
| `PANORAMAX_UUID_NAMESPACE` | a built-in fallback UUID |

!!! danger "Set this once, and never change it"
    Every published identifier is a pure function of this namespace and the
    row's primary key. Rotating it re-publishes the entire catalogue under new
    identifiers and orphans everything the federation has already harvested.

Generate one with `python -c "import uuid; print(uuid.uuid4())"` and treat it
like a database name: boring, permanent, and written down.

## Accuracy

| Setting | Default |
| --- | --- |
| `PANORAMAX_CONFIDENCE_ACCURACY_M` | `{"high": 25.0, "medium": 100.0, "low": 500.0}` |

Yesterdays records a contributor's confidence as low/medium/high; STAC's
quality extension wants metres. There is no measured conversion between the
two — these are deliberately pessimistic order-of-magnitude estimates,
published so consumers can tell a crowd-placed historical photograph from a GPS
track. Override them if you have calibrated your own contributors.

Values are merged over the defaults, so you can override one level:

```python
PANORAMAX_CONFIDENCE_ACCURACY_M = {"low": 1000.0}
```

## Paging

| Setting | Default |
| --- | --- |
| `PANORAMAX_PAGE_SIZE` | `100` |
| `PANORAMAX_MAX_PAGE_SIZE` | `1000` |

A client-supplied `limit` is clamped to `PANORAMAX_MAX_PAGE_SIZE`.
