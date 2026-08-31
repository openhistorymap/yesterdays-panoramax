"""The subset of Yesterdays' ``images`` models the adapter depends on."""

from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from edtf import parse_edtf
from edtf.parser.edtf_exceptions import EDTFParseException


class Source(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Collection(models.Model):
    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name="collections"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField()
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self):
        return reverse(
            "images:collection_detail",
            kwargs={"source_slug": self.source.slug, "collection_slug": self.slug},
        )


class License(models.Model):
    name = models.CharField(max_length=500)
    display_name = models.CharField(max_length=500)
    permalink = models.URLField(null=True, blank=True)


class Image(models.Model):
    ROTATION_CHOICES = [(0, "None"), (90, "90"), (180, "180"), (270, "270")]
    MIRROR_CHOICES = [("none", "None"), ("h", "Horizontal"), ("v", "Vertical")]

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="images"
    )
    title = models.CharField(max_length=500)
    permalink = models.URLField()
    thumbnail = models.URLField(null=True, blank=True)
    transformed_permalink = models.URLField(null=True, blank=True)
    original_url = models.URLField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    license = models.ForeignKey(
        License, null=True, blank=True, on_delete=models.SET_NULL, related_name="images"
    )
    creator = models.CharField(null=True, blank=True, max_length=100)
    ref = models.CharField(null=True, blank=True, max_length=100)

    original_date = models.CharField(null=True, blank=True, max_length=50)
    edtf_date = models.CharField(null=True, blank=True, max_length=50)
    start_decdate = models.IntegerField(null=True, blank=True)
    end_decdate = models.IntegerField(null=True, blank=True)

    aerial = models.BooleanField(default=False)
    will_not_georef = models.BooleanField(default=False)
    rotation = models.IntegerField(choices=ROTATION_CHOICES, default=0)
    mirror = models.CharField(max_length=4, choices=MIRROR_CHOICES, default="none")

    iiif_url = models.URLField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
    )
    is_searchable = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_transform(self):
        return self.rotation != 0 or self.mirror != "none"

    @property
    def display_permalink(self):
        return self.transformed_permalink or self.permalink

    def get_absolute_url(self):
        return reverse("images:image_detail", kwargs={"image_id": self.id})

    def save(self, *args, **kwargs):
        # start_decdate / end_decdate are the *years* bounding the EDTF range;
        # the adapter's temporal search filters on them.
        if self.edtf_date:
            try:
                parsed = parse_edtf(self.edtf_date)
            except EDTFParseException:
                self.start_decdate = self.end_decdate = None
            else:
                self.start_decdate = parsed.lower_strict()[0]
                self.end_decdate = parsed.upper_strict()[0]
        else:
            self.start_decdate = self.end_decdate = None

        # Changing a transform invalidates the derived assets.
        update_fields = kwargs.get("update_fields")
        if self.pk and (
            update_fields is None or {"rotation", "mirror"} & set(update_fields)
        ):
            previous = (
                Image.objects.filter(pk=self.pk).only("rotation", "mirror").first()
            )
            if previous and (
                previous.rotation != self.rotation or previous.mirror != self.mirror
            ):
                self.transformed_permalink = None
                self.thumbnail = None
                self.iiif_url = None
        super().save(*args, **kwargs)


class Georeference(models.Model):
    CONFIDENCE_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High")]

    image = models.ForeignKey(
        Image, on_delete=models.CASCADE, related_name="georeferences"
    )
    point = gis_models.PointField(spatial_index=True)
    direction = models.IntegerField(null=True, blank=True)
    confidence = models.CharField(
        max_length=10, choices=CONFIDENCE_CHOICES, default="medium"
    )
    georeferenced_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="georeferenced_images",
    )
    georeferenced_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# `is_searchable` is a denormalized "public collection AND public source AND not
# a duplicate" flag. The adapter reads it rather than recomputing it, so the
# stub has to maintain it the same way the real app does -- with update(), so
# no further signal fires.


def _searchable(image):
    return (
        image.collection.public
        and image.collection.source.public
        and image.duplicate_of_id is None
    )


@receiver(post_save, sender=Image)
def _image_searchable(sender, instance, **kwargs):
    value = _searchable(instance)
    if instance.is_searchable != value:
        Image.objects.filter(pk=instance.pk).update(is_searchable=value)


@receiver(post_save, sender=Collection)
def _collection_searchable(sender, instance, **kwargs):
    public = instance.public and instance.source.public
    Image.objects.filter(collection=instance, duplicate_of__isnull=True).update(
        is_searchable=public
    )
    Image.objects.filter(collection=instance, duplicate_of__isnull=False).update(
        is_searchable=False
    )


@receiver(post_save, sender=Source)
def _source_searchable(sender, instance, **kwargs):
    for collection in instance.collections.all():
        _collection_searchable(Collection, collection)
