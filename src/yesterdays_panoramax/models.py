"""Federation state for the collections this instance publishes.

The adapter keeps one row per collection it has ever published. The row exists
for three reasons, none of which can be answered from ``images`` alone:

**Tombstones.** The harvester removes a collection from the federation only
when it sees ``geovisio:status: "deleted"`` for it. Dropping a collection
silently out of the feed -- which is what happens when it is made private --
would leave it live in the central catalogue indefinitely. So a collection that
was published and is no longer eligible has to keep appearing in the feed,
flagged as deleted, and that requires remembering that it was once published.

**Change detection.** The harvester's incremental pass filters on the
*collection's* ``updated``, then re-fetches all of that collection's items.
``images.Collection.updated_at`` only moves when the collection row itself is
written, so a new georeference on one of its images would never propagate. This
row's ``updated`` is bumped for any change beneath the collection.

**Cheap listings.** The extent and item count are denormalized here so that
serving a page of collections is one indexed scan rather than an aggregate per
collection.

None of this touches the ``images`` tables, which is what lets the app be added
to an existing installation with a migration of its own and nothing else.
"""

from django.contrib.gis.db.models import Extent
from django.db import models, transaction
from django.utils import timezone

from . import conf, dates, hostmodels, ids, queries

# Re-exported so Django registers it: the app registry only imports
# `<app>.models`, and ImageDecision lives in its own module to keep
# queries -> decisions from becoming queries -> models -> queries.
from .decisions import ImageDecision  # noqa: F401


class PublishedCollection(models.Model):
    # The FK is for convenience; collection_pk is the identity. A deleted
    # collection nulls the FK (SET_NULL) but must leave the tombstone standing,
    # because the federation still has to be told the collection is gone.
    collection = models.OneToOneField(
        "images.Collection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="panoramax_state",
    )
    collection_pk = models.BigIntegerField(unique=True, editable=False)
    uuid = models.UUIDField(unique=True, editable=False)

    published = models.BooleanField(default=False, db_index=True)
    item_count = models.PositiveIntegerField(default=0)
    # SPDX id shared by every published image in the collection, or
    # conf.MIXED_LICENSE when they differ. Denormalized so that listing a page
    # of collections does not need a distinct-licence query per collection.
    license_label = models.CharField(max_length=100, blank=True, default="")

    created = models.DateTimeField()
    # Bumped on any change beneath the collection. Indexed because every
    # incremental harvest filters and sorts on it.
    updated = models.DateTimeField(db_index=True)
    first_published_at = models.DateTimeField(null=True, blank=True)
    unpublished_at = models.DateTimeField(null=True, blank=True)

    min_x = models.FloatField(null=True, blank=True)
    min_y = models.FloatField(null=True, blank=True)
    max_x = models.FloatField(null=True, blank=True)
    max_y = models.FloatField(null=True, blank=True)
    start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["updated", "collection_pk"]
        indexes = [
            # Named explicitly so the model agrees with the hand-written
            # migration; left to Django, these get hashed names and every
            # downstream `makemigrations --check` reports phantom drift.
            # The harvester's query: updated > T, ordered by updated.
            models.Index(
                fields=["updated", "collection_pk"],
                name="panoramax_updated_pk_idx",
            ),
            models.Index(
                fields=["published", "updated"], name="panoramax_pub_updated_idx"
            ),
        ]
        verbose_name = "published collection"

    def __str__(self):
        state = "published" if self.published else "withdrawn"
        return f"Collection {self.collection_pk} ({state})"

    @property
    def bbox(self):
        if None in (self.min_x, self.min_y, self.max_x, self.max_y):
            return None
        return [self.min_x, self.min_y, self.max_x, self.max_y]

    @property
    def is_tombstone(self) -> bool:
        """Withdrawn, but the federation may not have been told yet."""
        return not self.published

    @classmethod
    def refresh(cls, collection_pk, *, touch=True):
        """Recompute one collection's federation state.

        *touch* bumps ``updated``, which is what makes the next harvest pick the
        collection up. The backfill command passes ``touch=False`` so that
        importing existing state does not look like a site-wide edit and force
        a full re-harvest of every collection.

        Returns the row, or ``None`` when the collection is not and never was
        publishable -- no row is created for a collection with nothing to say.
        """
        images = queries.federatable_images_for(collection_pk)
        count = images.count()
        now = timezone.now()

        if count == 0:
            # Withdraw an existing row; stay silent about collections that were
            # never published.
            row = cls.objects.filter(collection_pk=collection_pk).first()
            if row is None:
                return None
            if row.published:
                row.published = False
                row.unpublished_at = now
                row.item_count = 0
                row.updated = now
                row.save(
                    update_fields=[
                        "published",
                        "unpublished_at",
                        "item_count",
                        "updated",
                    ]
                )
            return row

        # `created` should be the collection's own creation date, not the
        # moment federation happened, so that a backfill of an existing archive
        # publishes truthful dates rather than a wall of today's timestamp.
        created_at = (
            hostmodels.Collection.objects.filter(pk=collection_pk)
            .values_list("created_at", flat=True)
            .first()
        ) or now

        extent = images.aggregate(box=Extent("geo_point"))["box"]
        start, end = cls._temporal_extent(images)
        license_label = cls._license_label(images)

        row, created_now = cls.objects.get_or_create(
            collection_pk=collection_pk,
            defaults={
                "uuid": ids.collection_uuid(collection_pk),
                "collection_id": collection_pk,
                "created": created_at,
                "updated": now,
                "first_published_at": now,
                "published": True,
            },
        )

        row.collection_id = collection_pk
        row.item_count = count
        row.published = True
        row.unpublished_at = None
        if row.first_published_at is None:
            row.first_published_at = now
        if extent:
            row.min_x, row.min_y, row.max_x, row.max_y = extent
        row.start_datetime, row.end_datetime = start, end
        row.license_label = license_label
        if touch or created_now:
            row.updated = now
        row.save()
        return row

    @staticmethod
    def _license_label(images):
        """The collection's SPDX licence, or "other" when its images differ."""
        names = set(images.values_list("license__name", flat=True).distinct())
        spdx = {conf.spdx_for(name) for name in names}
        spdx.discard(None)
        if len(spdx) == 1:
            return spdx.pop()
        return conf.MIXED_LICENSE

    @staticmethod
    def _temporal_extent(images):
        """Span of an image queryset's EDTF dates.

        The dates only become timestamps once EDTF has been parsed, which the
        database cannot do, so this runs in Python -- over the *distinct* date
        strings rather than one per image, since an archival collection tends to
        reuse a handful of dates across thousands of photographs.
        """
        start = end = None
        for value in images.values_list("edtf_date", flat=True).distinct():
            lower, upper = dates.edtf_interval(value)
            if lower is None:
                continue
            start = lower if start is None else min(start, lower)
            end = upper if end is None else max(end, upper)
        return start, end

    @classmethod
    def touch(cls, collection_pk):
        """Mark a collection changed without recomputing its aggregates."""
        cls.objects.filter(collection_pk=collection_pk).update(updated=timezone.now())

    @classmethod
    def refresh_on_commit(cls, collection_pk):
        """Refresh once the surrounding transaction lands.

        Deferring matters: a signal firing mid-transaction would otherwise read
        rows the transaction is still writing, and would recompute repeatedly
        during a bulk import.
        """
        if collection_pk is None:
            return
        transaction.on_commit(lambda: cls.refresh(collection_pk))

    @classmethod
    def withdraw(cls, collection_pk):
        """Tombstone a collection whose row is being deleted outright."""
        now = timezone.now()
        cls.objects.filter(collection_pk=collection_pk, published=True).update(
            published=False, unpublished_at=now, item_count=0, updated=now
        )
