"""Building the STAC documents the federation reads.

Shapes here follow what a real Panoramax instance emits, checked against
``panoramax.openstreetmap.fr`` and ``api.panoramax.xyz`` rather than against
the prose documentation, because the harvester reads the JSON and not the docs.

A few mappings are judgement calls and are commented where they occur: which
asset stands in for Panoramax's fixed-width "SD" rendition, how a contributor's
confidence becomes a horizontal accuracy in metres, and why items are ordered
by identifier rather than by date.
"""

from django.urls import reverse

from . import conf, dates, ids

STAC_VERSION = "1.0.0"

VIEW_EXTENSION = "https://stac-extensions.github.io/view/v1.0.0/schema.json"
PERSPECTIVE_EXTENSION = (
    "https://stac-extensions.github.io/perspective-imagery/v1.0.0/schema.json"
)
QUALITY_EXTENSION = "https://stac.linz.govt.nz/v0.0.15/quality/schema.json"
STATS_EXTENSION = "https://stac-extensions.github.io/stats/v0.2.0/schema.json"

CONFORMS_TO = [
    "https://api.stacspec.org/v1.0.0/core",
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
    "https://api.stacspec.org/v1.0.0/item-search",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]

_MEDIA_TYPES = {
    "webp": "image/webp",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}


def absolute(request, path):
    return request.build_absolute_uri(path)


def tile_template(request):
    """The XYZ template advertised to viewers.

    Built from the landing route rather than written out, so it follows the
    app wherever it is mounted -- even though the harvester obliges that to be
    ``/api/``.
    """
    return absolute(request, reverse("panoramax:landing") + "map/{z}/{x}/{y}.mvt")


def media_type(url):
    """Guess an asset's media type from its extension.

    Panoramax accepts ``image/jpeg`` and ``image/webp``; Yesterdays writes its
    derivatives as WebP and its originals as whatever the archive supplied.
    """
    if not url:
        return "image/jpeg"
    tail = url.split("?", 1)[0].rsplit(".", 1)
    if len(tail) != 2:
        return "image/jpeg"
    return _MEDIA_TYPES.get(tail[1].lower(), "image/jpeg")


# --------------------------------------------------------------------------
# Landing page and instance configuration
# --------------------------------------------------------------------------


def landing(request):
    """The STAC catalogue root, served at ``/api``."""
    root = absolute(request, reverse("panoramax:landing"))
    collections = absolute(request, reverse("panoramax:collections"))
    return {
        "type": "Catalog",
        "stac_version": STAC_VERSION,
        "id": "yesterdays",
        "title": conf.instance_name(),
        "description": conf.instance_description(),
        "conformsTo": CONFORMS_TO,
        "links": [
            {"rel": "root", "type": "application/json", "href": root},
            {"rel": "self", "type": "application/json", "href": root},
            {"rel": "data", "type": "application/json", "href": collections},
            {
                "rel": "search",
                "type": "application/geo+json",
                "href": absolute(request, reverse("panoramax:search")),
            },
            {
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/queryables",
                "type": "application/schema+json",
                "title": "Queryables",
                "href": absolute(request, reverse("panoramax:queryables")),
            },
            {
                "rel": "xyz",
                "type": "application/vnd.mapbox-vector-tile",
                "title": "Pictures and sequences vector tiles",
                "href": tile_template(request),
            },
            {
                "rel": "xyz-style",
                "type": "application/json",
                "title": "MapLibre Style JSON",
                "href": absolute(request, reverse("panoramax:style")),
            },
        ],
    }


def _localized(value):
    """Panoramax's ``{"label": ..., "langs": {...}}`` shape."""
    return {"label": value, "langs": {"en": value}}


def configuration(request):
    """``/api/configuration`` -- re-read by the harvester once a day."""
    document = {
        "name": _localized(conf.instance_name()),
        "description": _localized(conf.instance_description()),
        "color": conf.color(),
        "license": {"id": conf.license_id(), "url": conf.license_url()},
        # Yesterdays is an archive of scanned photographs, not a capture
        # target: nobody uploads field pictures to it through the Panoramax
        # clients, so the instance advertises no registration and no upload.
        "auth": {"enabled": False, "registration_is_open": False},
        "pages": [],
    }
    if conf.logo():
        document["logo"] = conf.logo()
    if conf.contact_email():
        document["email"] = conf.contact_email()
    if conf.geo_coverage():
        document["geo_coverage"] = _localized(conf.geo_coverage())
    return document


# --------------------------------------------------------------------------
# Collections
# --------------------------------------------------------------------------


def collection_document(row, request, *, collection=None):
    """A STAC Collection for one :class:`~panoramax.models.PublishedCollection`.

    A withdrawn collection is published as a tombstone carrying
    ``geovisio:status: "deleted"``. That flag is the only thing that removes a
    collection from the central catalogue -- the harvester treats a collection
    that has merely vanished from the feed as unchanged, so it would otherwise
    stay in the federation forever.
    """
    root = absolute(request, reverse("panoramax:landing"))
    self_href = absolute(request, reverse("panoramax:collection", args=[str(row.uuid)]))

    if row.is_tombstone:
        return {
            "type": "Collection",
            "stac_version": STAC_VERSION,
            "id": str(row.uuid),
            "geovisio:status": "deleted",
            "description": "This collection is no longer published.",
            "license": row.license_label or conf.license_id(),
            "extent": {
                "spatial": {"bbox": [row.bbox or [-180.0, -90.0, 180.0, 90.0]]},
                "temporal": {"interval": [[None, None]]},
            },
            "created": dates.rfc3339(row.created),
            "updated": dates.rfc3339(row.updated),
            "links": [
                {"rel": "root", "type": "application/json", "href": root},
                {"rel": "self", "type": "application/json", "href": self_href},
            ],
        }

    collection = collection or row.collection
    source = collection.source if collection else None

    document = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [STATS_EXTENSION, QUALITY_EXTENSION],
        "id": str(row.uuid),
        "title": collection.name if collection else str(row.uuid),
        "description": (collection.description if collection else "")
        or "Georeferenced historical photographs",
        "license": row.license_label or conf.license_id(),
        "geovisio:status": "ready",
        "keywords": ["pictures", "historical"],
        "extent": {
            "spatial": {"bbox": [row.bbox or [-180.0, -90.0, 180.0, 90.0]]},
            "temporal": {
                "interval": [
                    [dates.rfc3339(row.start_datetime), dates.rfc3339(row.end_datetime)]
                ]
            },
        },
        "created": dates.rfc3339(row.created),
        "updated": dates.rfc3339(row.updated),
        "stats:items": {"count": row.item_count},
        "summaries": {},
        "semantics": [],
        "links": [
            {"rel": "root", "type": "application/json", "href": root},
            {"rel": "parent", "type": "application/json", "href": root},
            {"rel": "self", "type": "application/json", "href": self_href},
            {
                "rel": "items",
                "type": "application/geo+json",
                "title": "Pictures in this collection",
                "href": absolute(
                    request, reverse("panoramax:items", args=[str(row.uuid)])
                ),
            },
            {
                "rel": "license",
                "href": conf.license_url(),
                "title": f"License for this object ({row.license_label})",
            },
        ],
    }

    if source:
        provider = {"name": source.name, "roles": ["producer"]}
        if source.url:
            provider["url"] = source.url
        document["providers"] = [provider]
    if collection:
        # Survives harvesting (the crawler keeps every rel it does not
        # recompute), so the federation keeps a route back to the record.
        document["links"].append(
            {
                "rel": "via",
                "type": "text/html",
                "title": "This collection on Yesterdays",
                "href": absolute(request, collection.get_absolute_url()),
            }
        )
    return document


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def _dimensions(image):
    """Pixel dimensions of the asset we actually serve.

    ``width``/``height`` describe the original scan, but the ``hd`` asset is
    ``display_permalink`` -- the transformed rendition -- so a quarter-turn
    rotation swaps them.
    """
    if not image.width or not image.height:
        return None
    if image.rotation in (90, 270):
        return [image.height, image.width]
    return [image.width, image.height]


def _assets(image):
    """Panoramax's three renditions, mapped onto what Yesterdays stores.

    ``sd`` is Panoramax's fixed 2048px-wide rendition. Yesterdays generates no
    such intermediate -- only a full-size transformed image and a 500px
    thumbnail -- so ``sd`` points at the full-size asset. The role is what the
    viewer selects on, and serving a larger image than advertised degrades
    bandwidth rather than correctness; the alternative, omitting the ``visual``
    role entirely, breaks viewers outright.
    """
    full = image.display_permalink
    thumb = image.thumbnail or full
    return {
        "hd": {
            "href": full,
            "type": media_type(full),
            "roles": ["data"],
            "title": "HD picture",
            "description": "Highest resolution available of this picture",
        },
        "sd": {
            "href": full,
            "type": media_type(full),
            "roles": ["visual"],
            "title": "SD picture",
            "description": "Standard definition rendition",
        },
        "thumb": {
            "href": thumb,
            "type": media_type(thumb),
            "roles": ["thumbnail"],
            "title": "Thumbnail",
            "description": "Picture in low definition (500px longest side)",
        },
    }


def item_document(image, request, *, collection_uuid, neighbours=(None, None)):
    """A STAC Item for one georeferenced image.

    *neighbours* is ``(previous, next)`` image ids within the collection; the
    viewer walks a sequence through those links.
    """
    item_uuid = ids.image_uuid(image.pk)
    root = absolute(request, reverse("panoramax:landing"))
    collection_href = absolute(
        request, reverse("panoramax:collection", args=[collection_uuid])
    )
    self_href = absolute(
        request,
        reverse("panoramax:item", args=[collection_uuid, str(item_uuid)]),
    )

    point = image.geo_point
    start, end = dates.edtf_interval(image.edtf_date)
    spdx = conf.spdx_for(image.license.name if image.license_id else None)

    properties = {
        "datetime": dates.rfc3339(start),
        "created": dates.rfc3339(image.created_at),
        "updated": dates.rfc3339(image.updated_at),
        "title": image.title,
        "license": spdx or conf.license_id(),
        "geovisio:status": "ready",
        "geovisio:image": image.display_permalink,
        "geovisio:thumbnail": image.thumbnail or image.display_permalink,
        # The harvester flattens these; emitting them empty keeps its SQL from
        # having to cope with a missing key.
        "semantics": [],
        "annotations": [],
        # The EDTF string is the archive's own assertion about the date, which
        # no STAC field can carry without losing its qualifiers ("1890s",
        # "192X", "before 1901"). Published verbatim alongside the timestamps.
        "yesterdays:edtf": image.edtf_date,
        "yesterdays:image_id": image.pk,
    }

    # A date that resolves to a range rather than an instant is published as
    # one, with `datetime` pinned to the start. See panoramax.dates.
    if start and end and not dates.is_instant(start, end):
        properties["start_datetime"] = dates.rfc3339(start)
        properties["end_datetime"] = dates.rfc3339(end)

    if image.description:
        properties["description"] = image.description
    if image.creator:
        properties["geovisio:producer"] = image.creator

    if image.geo_direction is not None:
        properties["view:azimuth"] = image.geo_direction

    dimensions = _dimensions(image)
    if dimensions:
        # No field_of_view: these are flat photographs. The meta-catalogue
        # keys off `field_of_view == 360` to classify a picture as
        # equirectangular, so setting it would misfile every image.
        properties["pers:interior_orientation"] = {
            "sensor_array_dimensions": dimensions
        }

    accuracy = conf.confidence_accuracy().get(image.geo_confidence)
    if accuracy is not None:
        properties["quality:horizontal_accuracy"] = accuracy
        properties["quality:horizontal_accuracy_type"] = "estimated"
        properties["yesterdays:confidence"] = image.geo_confidence

    links = [
        {"rel": "root", "type": "application/json", "href": root},
        {"rel": "self", "type": "application/geo+json", "href": self_href},
        {"rel": "collection", "type": "application/json", "href": collection_href},
        {"rel": "parent", "type": "application/json", "href": collection_href},
        {
            "rel": "license",
            "href": conf.license_url(),
            "title": f"License for this object ({spdx or conf.license_id()})",
        },
        {
            "rel": "via",
            "type": "text/html",
            "title": "This picture on Yesterdays",
            "href": absolute(request, image.get_absolute_url()),
        },
    ]
    previous_id, next_id = neighbours
    for rel, neighbour in (("prev", previous_id), ("next", next_id)):
        if neighbour is not None:
            links.append(
                {
                    "rel": rel,
                    "type": "application/geo+json",
                    "id": str(ids.image_uuid(neighbour)),
                    "href": absolute(
                        request,
                        reverse(
                            "panoramax:item",
                            args=[collection_uuid, str(ids.image_uuid(neighbour))],
                        ),
                    ),
                }
            )

    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "stac_extensions": [
            VIEW_EXTENSION,
            PERSPECTIVE_EXTENSION,
            QUALITY_EXTENSION,
        ],
        "id": str(item_uuid),
        "collection": collection_uuid,
        "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
        "bbox": [point.x, point.y, point.x, point.y],
        "properties": properties,
        "assets": _assets(image),
        "links": links,
    }
