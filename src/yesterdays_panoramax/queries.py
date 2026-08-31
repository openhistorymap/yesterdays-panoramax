"""Which rows are eligible to be published, and how their position is chosen.

Two rules are worth stating explicitly, because both are decisions rather than
mechanics:

**Which georeference wins.** An ``images.Image`` can carry many
``Georeference`` rows -- several contributors, later corrections, differing
confidence -- but a STAC item has one geometry and one azimuth. We take the
most recently submitted georeference, which is the same rule the rest of the
site already applies (it is what ``public_georeferences_mvt`` encodes for the
map tiles and the GeoJSON endpoints). Publishing a different point from the one
the site itself displays would be a bug that is very hard to see. We query it
through the ORM rather than reading that materialized view, because the view is
refreshed asynchronously and lacks the columns this app filters on -- the rule
is shared, the plumbing is not.

**Which images may be published at all.** Panoramax's federation policy expects
an open licence, and Yesterdays holds images under many licences that do not
qualify. Publication is therefore opt-in per licence via
``PANORAMAX_LICENSE_ALLOWLIST``; with the setting unset nothing is eligible.
Aerials are excluded because Panoramax catalogues street-level views, and
undated images are excluded because the catalogue's ``datetime`` column is
``NOT NULL``.
"""

from django.contrib.gis.db.models import PointField
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Lower

from . import conf, hostmodels
from .decisions import EXCLUDE, INCLUDE


def _latest_georeference():
    """Subquery source for the winning georeference of the outer image."""
    # Ordering by id as well keeps the choice deterministic when two
    # georeferences share a timestamp, which bulk imports can produce.
    return hostmodels.Georeference.objects.filter(image=OuterRef("pk")).order_by(
        "-georeferenced_at", "-id"
    )


def with_georeference(queryset):
    """Annotate each image with its winning georeference's fields."""
    latest = _latest_georeference()
    return queryset.annotate(
        # output_field is explicit because this annotation is both aggregated
        # over (Extent, for a collection's bbox) and filtered with a spatial
        # lookup (bbox search); neither can be resolved from a bare Subquery.
        geo_point=Subquery(
            latest.values("point")[:1], output_field=PointField(srid=4326)
        ),
        geo_direction=Subquery(latest.values("direction")[:1]),
        geo_confidence=Subquery(latest.values("confidence")[:1]),
        geo_updated=Subquery(latest.values("updated_at")[:1]),
    )


def federatable_images():
    """Every image this instance is willing to publish.

    Returns an empty queryset -- not an unfiltered one -- whenever the adapter
    is disabled or no licence has been allowed, so that a half-configured
    install publishes nothing rather than everything.
    """
    allowed = conf.license_allowlist()
    images = hostmodels.Image
    if not conf.enabled() or not allowed:
        return images.objects.none()

    queryset = (
        images.objects.annotate(license_key=Lower("license__name"))
        .filter(
            # is_searchable is the denormalized "public collection AND public
            # source AND not a duplicate" flag maintained by images.signals.
            is_searchable=True,
            aerial=False,
            will_not_georef=False,
            license_key__in=list(allowed),
        )
        .exclude(edtf_date__isnull=True)
        .exclude(edtf_date="")
        .exclude(permalink="")
    )
    queryset = apply_image_policy(queryset)
    return with_georeference(queryset).filter(geo_point__isnull=False)


def apply_image_policy(queryset):
    """Apply per-image rulings on top of the property-based rules.

    Under ``opt-out`` an image with no ruling is unaffected -- which is what
    makes the feature optional: until somebody rules on something, this filter
    changes nothing.
    """
    if conf.image_policy() == conf.OPT_IN:
        return queryset.filter(panoramax_decision__decision=INCLUDE)
    return queryset.exclude(panoramax_decision__decision=EXCLUDE)


def federatable_images_for(collection_pk):
    return federatable_images().filter(collection_id=collection_pk)


def federatable_collection_ids():
    """Primary keys of collections that currently have something to publish."""
    if not conf.enabled():
        return hostmodels.Collection.objects.none().values_list("pk", flat=True)
    return federatable_images().values_list("collection_id", flat=True).distinct()


def collection_is_federatable(collection_pk) -> bool:
    return federatable_images_for(collection_pk).exists()
