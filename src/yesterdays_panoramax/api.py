"""Setting per-image federation decisions from host code.

This package cannot add a checkbox to Yesterdays' own image page -- that
template belongs to the host. What it can do is offer a small, stable surface
for the host to call from its own views, admin actions or API, so that the
decision has one home and one meaning.

    from yesterdays_panoramax import api

    api.exclude_image(image, reason="Depicted person objected", by=request.user)
    api.clear_decision(image)
    api.is_published(image)

Every call schedules the collection refresh that carries the change into the
federation, so callers do not have to know that federation state exists.
"""

from . import queries
from .decisions import EXCLUDE, INCLUDE, ImageDecision


def _pk(image):
    return image if isinstance(image, int) else image.pk


def _set(image, decision, *, reason, by):
    obj, _ = ImageDecision.objects.update_or_create(
        image_id=_pk(image),
        defaults={"decision": decision, "reason": reason, "decided_by": by},
    )
    return obj


def exclude_image(image, *, reason="", by=None) -> ImageDecision:
    """Hold this image back from the federation, whatever the rules say.

    Takes effect on the next harvest: the picture drops out of its collection's
    item listing and the harvester, which replaces a collection's items
    wholesale, deletes it from the central catalogue.
    """
    return _set(image, EXCLUDE, reason=reason, by=by)


def include_image(image, *, reason="", by=None) -> ImageDecision:
    """Approve this image.

    Required under ``PANORAMAX_IMAGE_POLICY = "opt-in"``; under the default
    ``opt-out`` it records approval explicitly but changes nothing, since an
    image with no ruling is already publishable.
    """
    return _set(image, INCLUDE, reason=reason, by=by)


def clear_decision(image) -> bool:
    """Drop any ruling, returning the image to the ordinary rules.

    Returns whether there was one to drop.
    """
    deleted, _ = ImageDecision.objects.filter(image_id=_pk(image)).delete()
    return bool(deleted)


def decision_for(image) -> str | None:
    """``"include"``, ``"exclude"``, or ``None`` when nobody has ruled."""
    return (
        ImageDecision.objects.filter(image_id=_pk(image))
        .values_list("decision", flat=True)
        .first()
    )


def is_published(image) -> bool:
    """Whether this image is currently publishable.

    The whole test, not just the ruling: licence, visibility, date,
    georeference and policy. This is what a host UI should show, because an
    image can be approved and still not published -- for want of a
    georeference, say.
    """
    return queries.federatable_images().filter(pk=_pk(image)).exists()
