"""Deployment settings for the Panoramax federation adapter.

Every value is read from ``django.conf.settings`` at call time so a deployment
can configure the adapter without editing this app, and so ``override_settings``
works in tests. Nothing here is required to have a value: an installation that
adds ``panoramax`` to ``INSTALLED_APPS`` and nothing else gets a working but
unpublished instance, which is the safe default.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Fallback namespace for the identifier scheme. Deployments should set
# PANORAMAX_UUID_NAMESPACE to a value of their own and never change it
# afterwards: it is what makes a picture's federated identity stable, and
# rotating it re-publishes the whole catalogue under new identifiers.
DEFAULT_UUID_NAMESPACE = uuid.UUID("6f3d6b1a-6b0e-5a3f-9c8d-0f1c2a4b8e7d")

# Panoramax's federation policy expects instances to publish under an open
# licence. The adapter refuses to publish an image whose licence is not named
# here, so the default of "nothing is allowed" cannot leak a restrictively
# licensed archive into the federation by accident.
DEFAULT_LICENSE_ALLOWLIST: dict[str, str] = {}

# What a collection's licence is called when its images do not all share one.
# STAC reserves "other" for exactly this.
MIXED_LICENSE = "other"

#: Publish everything the eligibility rules allow, minus explicit exclusions.
OPT_OUT = "opt-out"
#: Publish nothing but explicitly approved images. For archives whose rights
#: are decided picture by picture rather than licence by licence.
OPT_IN = "opt-in"
IMAGE_POLICIES = (OPT_OUT, OPT_IN)

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


def _get(name, default):
    return getattr(settings, name, default)


def enabled() -> bool:
    """Whether the federation endpoints serve data.

    When false the endpoints still respond — the harvester and the viewer both
    cope better with an empty catalogue than with a 404 — but no collection is
    ever eligible, so nothing is published.
    """
    return bool(_get("PANORAMAX_ENABLED", False))


def instance_name() -> str:
    return _get("PANORAMAX_INSTANCE_NAME", "Yesterdays")


def instance_description() -> str:
    return _get(
        "PANORAMAX_DESCRIPTION",
        "Georeferenced historical photographs",
    )


def uuid_namespace() -> uuid.UUID:
    value = _get("PANORAMAX_UUID_NAMESPACE", DEFAULT_UUID_NAMESPACE)
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def license_id() -> str:
    return _get("PANORAMAX_LICENSE_ID", "CC-BY-SA-4.0")


def license_url() -> str:
    return _get(
        "PANORAMAX_LICENSE_URL",
        "https://creativecommons.org/licenses/by-sa/4.0/",
    )


def license_allowlist() -> dict[str, str]:
    """``images.License`` names that may be federated, mapped to SPDX ids.

    This setting does two jobs at once, because both need the same list.
    It is the *gate*: Yesterdays holds images under a wide range of licences,
    most of which Panoramax's federation policy will not accept, so publication
    is opt-in per licence and an unset allowlist publishes nothing. It is also
    the *translation*: ``License.name`` is free text chosen by whoever entered
    the archive, while STAC wants an SPDX identifier, and only a human knows
    that "CC BY-SA 4.0" and "Creative Commons Attribution-ShareAlike 4.0" are
    the same licence.

    Configure it as a mapping::

        PANORAMAX_LICENSE_ALLOWLIST = {
            "CC BY-SA 4.0": "CC-BY-SA-4.0",
            "No known copyright restrictions": "CC0-1.0",
        }

    A plain sequence of names is also accepted, in which case every listed
    licence is published under ``PANORAMAX_LICENSE_ID``. Keys are matched
    case-insensitively against ``License.name``.
    """
    raw = _get("PANORAMAX_LICENSE_ALLOWLIST", DEFAULT_LICENSE_ALLOWLIST)
    if isinstance(raw, dict):
        pairs = raw.items()
    else:
        pairs = ((name, None) for name in raw)
    return {
        name.strip().lower(): (spdx or license_id())
        for name, spdx in pairs
        if name and name.strip()
    }


def spdx_for(license_name) -> str | None:
    """The SPDX id configured for an ``images.License`` name, if allowed."""
    if not license_name:
        return None
    return license_allowlist().get(str(license_name).strip().lower())


def confidence_accuracy() -> dict[str, float]:
    """Horizontal accuracy in metres for each georeference confidence level.

    Yesterdays records a contributor's confidence as low/medium/high; STAC's
    quality extension wants metres. There is no measured conversion between
    the two -- these are deliberately pessimistic order-of-magnitude estimates,
    published so that consumers can tell a crowd-placed historical photograph
    from a GPS track. Deployments that have calibrated their own contributors
    should override the setting.
    """
    default = {"high": 25.0, "medium": 100.0, "low": 500.0}
    return {**default, **_get("PANORAMAX_CONFIDENCE_ACCURACY_M", {})}


def image_policy() -> str:
    """How per-image decisions combine with the eligibility rules.

    ``"opt-out"`` (the default) publishes everything eligible except images
    explicitly excluded. ``"opt-in"`` inverts it: nothing is published until an
    image has been explicitly approved, which is what an archive wants when
    rights are settled picture by picture rather than licence by licence.

    A bad value raises rather than falling back. Silently defaulting a typo to
    ``opt-out`` would publish an entire archive that somebody meant to curate,
    and the federation does not forget quickly.
    """
    value = str(_get("PANORAMAX_IMAGE_POLICY", OPT_OUT)).strip().lower()
    if value not in IMAGE_POLICIES:
        raise ImproperlyConfigured(
            f"PANORAMAX_IMAGE_POLICY must be one of {IMAGE_POLICIES!r}, not {value!r}"
        )
    return value


def logo() -> str | None:
    return _get("PANORAMAX_LOGO", None)


def color() -> str:
    return _get("PANORAMAX_COLOR", "#525252")


def contact_email() -> str | None:
    return _get("PANORAMAX_CONTACT_EMAIL", None)


def geo_coverage() -> str | None:
    return _get("PANORAMAX_GEO_COVERAGE", None)


def page_size() -> int:
    return max(1, int(_get("PANORAMAX_PAGE_SIZE", DEFAULT_PAGE_SIZE)))


def max_page_size() -> int:
    return max(1, int(_get("PANORAMAX_MAX_PAGE_SIZE", MAX_PAGE_SIZE)))


def clamp_limit(raw, default=None) -> int:
    """Coerce a client-supplied ``limit`` into an acceptable page size."""
    fallback = default if default is not None else page_size()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(value, max_page_size()))
