"""Keeping PublishedCollection in step with the catalogue.

Everything here hangs off ``images`` models but lives in this app, so adding
the adapter to an installation needs no edit to ``images/signals.py``.

Two behaviours are deliberate:

*Refreshes are deferred to commit.* ``images.models`` maintains
``Image.is_searchable`` in its own ``post_save`` receivers via ``update()``, and
eligibility depends on that flag. Running after commit means we read the
settled value rather than racing another receiver, and it keeps a bulk import
from recomputing the same collection once per row.

*Refreshes are batched per transaction.* An import that writes thousands of
images into one collection performs one refresh, not thousands.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from . import hostmodels
from .decisions import ImageDecision
from .models import PublishedCollection

logger = logging.getLogger(__name__)

# Image fields that can change what we publish, either by moving the image in
# or out of eligibility or by changing the STAC item we would emit for it. A
# save restricted (via update_fields) to anything else -- an embedding, a
# search vector, a skip counter -- is not a federation event.
RELEVANT_IMAGE_FIELDS = {
    "collection",
    "license",
    "edtf_date",
    "permalink",
    "transformed_permalink",
    "thumbnail",
    "iiif_url",
    "width",
    "height",
    "rotation",
    "mirror",
    "asset_generation",
    "aerial",
    "will_not_georef",
    "duplicate_of",
    "is_searchable",
    "title",
    "description",
    "creator",
    "original_url",
    "ref",
}

# The set of collections awaiting a refresh, parked on the database connection
# (which is already per-thread) for the life of the transaction.
_PENDING = "_panoramax_pending_collections"


def _schedule(collection_pks):
    """Queue a post-commit refresh of each collection named."""
    pks = {pk for pk in collection_pks if pk is not None}
    if not pks:
        return

    connection = transaction.get_connection()
    pending = getattr(connection, _PENDING, None)
    if pending is None:
        pending = set()
        setattr(connection, _PENDING, pending)
    pending.update(pks)

    # A callback is registered on *every* call, even though only the first one
    # to run does any work -- whichever fires first drains the whole set and
    # the rest find it empty. The obvious optimisation, a "already registered"
    # flag, is a trap: when a transaction rolls back Django discards the queued
    # callbacks but nothing resets the flag, so every subsequent change in that
    # thread would be silently dropped for the life of the process. Leaving
    # duplicate registrations costs a few no-op calls and cannot wedge.
    transaction.on_commit(_flush)


def _flush():
    connection = transaction.get_connection()
    pending = getattr(connection, _PENDING, None)
    if not pending:
        return
    # Drain before refreshing, so the later callbacks from this same commit
    # find nothing to do.
    pks = sorted(pending)
    pending.clear()
    for pk in pks:
        # Log but don't raise: the write that triggered this has already
        # committed, and a failed refresh only means the collection is stale
        # until the next event or the next run of `panoramax_backfill`.
        try:
            PublishedCollection.refresh(pk)
        except Exception:
            logger.warning(
                "Failed to refresh federation state for collection %s",
                pk,
                exc_info=True,
            )


def _collection_id_of_image(image_id):
    return (
        hostmodels.Image.objects.filter(pk=image_id)
        .values_list("collection_id", flat=True)
        .first()
    )


@receiver(post_save, sender=hostmodels.Georeference)
@receiver(post_delete, sender=hostmodels.Georeference)
def federation_on_georeference_change(sender, instance, **kwargs):
    """A georeference is what gives an image a geometry and an azimuth.

    On a cascading delete the image row may already be gone, in which case the
    Image receiver below covers the same collection.
    """
    _schedule([_collection_id_of_image(instance.image_id)])


@receiver(post_save, sender=ImageDecision)
@receiver(post_delete, sender=ImageDecision)
def federation_on_decision_change(sender, instance, **kwargs):
    """A ruling on one image changes what its collection publishes.

    Without this the decision would sit in the database and never reach the
    federation: the harvester only re-fetches a collection whose `updated` has
    moved, and nothing in `images` was written.
    """
    _schedule([_collection_id_of_image(instance.image_id)])


@receiver(pre_save, sender=hostmodels.Image)
def capture_previous_collection(sender, instance, **kwargs):
    """Remember the collection an image is leaving, so both ends refresh."""
    instance._panoramax_previous_collection_id = None
    update_fields = kwargs.get("update_fields")
    if instance.pk and (update_fields is None or "collection" in update_fields):
        instance._panoramax_previous_collection_id = _collection_id_of_image(
            instance.pk
        )


@receiver(post_save, sender=hostmodels.Image)
def federation_on_image_save(sender, instance, **kwargs):
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and not (RELEVANT_IMAGE_FIELDS & set(update_fields)):
        return
    previous = getattr(instance, "_panoramax_previous_collection_id", None)
    _schedule({instance.collection_id, previous})


@receiver(post_delete, sender=hostmodels.Image)
def federation_on_image_delete(sender, instance, **kwargs):
    _schedule([instance.collection_id])


@receiver(post_save, sender=hostmodels.Collection)
def federation_on_collection_save(sender, instance, **kwargs):
    _schedule([instance.pk])


@receiver(post_delete, sender=hostmodels.Collection)
def federation_on_collection_delete(sender, instance, **kwargs):
    # The refresh finds no eligible images and tombstones the row, which is
    # what tells the next harvest to drop the collection from the federation.
    _schedule([instance.pk])


@receiver(post_save, sender=hostmodels.Source)
def federation_on_source_save(sender, instance, **kwargs):
    """A source going private withdraws every collection beneath it."""
    _schedule(
        hostmodels.Collection.objects.filter(source_id=instance.pk).values_list(
            "pk", flat=True
        )
    )
