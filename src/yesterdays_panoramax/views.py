"""The endpoints the Panoramax harvester and viewer call.

The harvester only ever issues four requests -- ``/api/configuration``,
``/api/collections`` (bare, then filtered by ``updated``), and each
collection's ``/items`` -- following ``links[rel="next"]`` to exhaust a
listing. Everything else here exists for the web viewer and for humans
browsing the catalogue.

Pagination is keyset rather than offset throughout. The harvester walks an
entire catalogue while it is being written to, and offsets skip or repeat rows
when something is inserted mid-walk.

When the adapter is disabled the endpoints still answer, with an empty
catalogue. A 404 makes a harvester log an error and an operator go looking for
a broken deployment; an empty catalogue is the honest description of an
instance that has published nothing.
"""

from django.contrib.gis.geos import Polygon
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.http import urlencode
from django.views.decorators.http import require_GET

from . import conf, filters, ids, queries, stac, tiles
from .models import PublishedCollection

GEOJSON = "application/geo+json"

# The harvester re-reads collections whenever `updated` moves, so a short
# shared cache is safe and keeps a crawl of a large catalogue cheap.
CACHE_CONTROL = "public, max-age=60"


def _json(payload, *, content_type="application/json"):
    response = JsonResponse(payload, content_type=content_type)
    response["Cache-Control"] = CACHE_CONTROL
    return response


def _with_query(request, path, **params):
    """Absolute URL for *path*, carrying *params* as the query string.

    Properly encoded, which matters more than it looks: the harvester echoes
    our ``rel="next"`` href back verbatim, and the ``filter`` we round-trip
    into it is full of spaces and quotes.
    """
    query = urlencode({key: value for key, value in params.items() if value})
    return request.build_absolute_uri(f"{path}?{query}" if query else path)


# --------------------------------------------------------------------------
# Catalogue root
# --------------------------------------------------------------------------


@require_GET
def landing(request):
    return _json(stac.landing(request))


@require_GET
def configuration(request):
    return _json(stac.configuration(request))


@require_GET
def queryables(request):
    """Advertises the two properties the harvester filters collections on."""
    return _json(
        {
            "$schema": "https://json-schema.org/draft/2019-09/schema",
            "$id": request.build_absolute_uri(reverse("panoramax:queryables")),
            "type": "object",
            "title": "Queryables for the Yesterdays STAC API",
            "description": "Queryable names for the collection filter.",
            "properties": {
                "created": {
                    "description": "Creation date of the collection.",
                    "type": "string",
                    "anyOf": [{"format": "date-time"}, {"format": "date"}],
                },
                "updated": {
                    "description": "Update date of the collection.",
                    "type": "string",
                    "anyOf": [{"format": "date-time"}, {"format": "date"}],
                },
            },
            "additionalProperties": False,
        },
        content_type="application/schema+json",
    )


# --------------------------------------------------------------------------
# Collections
# --------------------------------------------------------------------------


def _decode_page(raw):
    """Keyset cursor for the collection listing: ``<updated>|<pk>``."""
    if not raw or "|" not in raw:
        return None, None
    moment, _, pk = raw.partition("|")
    parsed = parse_datetime(moment)
    try:
        return parsed, int(pk)
    except (TypeError, ValueError):
        return None, None


@require_GET
def collections(request):
    limit = conf.clamp_limit(request.GET.get("limit"))
    parsed = filters.parse(request.GET.get("filter"))

    queryset = filters.apply(
        PublishedCollection.objects.select_related("collection__source"), parsed
    ).order_by("updated", "collection_pk")

    after_updated, after_pk = _decode_page(request.GET.get("page"))
    if after_updated is not None:
        # Strict keyset on the compound sort key, so a page boundary that falls
        # inside a run of identical timestamps neither repeats nor skips.
        queryset = queryset.filter(
            Q(updated__gt=after_updated)
            | Q(updated=after_updated, collection_pk__gt=after_pk)
        )

    rows = list(queryset[: limit + 1])
    has_more, rows = len(rows) > limit, rows[:limit]

    documents = [stac.collection_document(row, request) for row in rows]

    links = [
        {
            "rel": "root",
            "type": "application/json",
            "href": request.build_absolute_uri(reverse("panoramax:landing")),
        },
        {
            "rel": "self",
            "type": "application/json",
            "href": request.build_absolute_uri(),
        },
    ]
    if has_more and rows:
        last = rows[-1]
        links.append(
            {
                "rel": "next",
                "type": "application/json",
                "href": _with_query(
                    request,
                    reverse("panoramax:collections"),
                    limit=limit,
                    filter=request.GET.get("filter", ""),
                    page=f"{last.updated.isoformat()}|{last.collection_pk}",
                ),
            }
        )
    return _json({"collections": documents, "links": links})


def _row_or_404(collection_uuid):
    try:
        pk = ids.decode_kind(collection_uuid, ids.COLLECTION)
    except ids.InvalidFederatedId:
        # `from None`: a UUID this instance did not mint is a plain 404, not an
        # internal error worth chaining a traceback onto.
        raise Http404("unknown collection") from None
    row = (
        PublishedCollection.objects.select_related("collection__source")
        .filter(collection_pk=pk)
        .first()
    )
    if row is None:
        raise Http404("unknown collection")
    return row


@require_GET
def collection(request, collection_uuid):
    return _json(stac.collection_document(_row_or_404(collection_uuid), request))


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def _ordered_items(collection_pk):
    """Eligible images of a collection, in a stable published order.

    Ordered by primary key. Chronological order would read better, but an
    archival collection's dates are EDTF strings whose only sortable projection
    in the database is the year, so it would neither be a true chronology nor a
    unique key -- and a keyset cursor needs a unique key.
    """
    return (
        queries.federatable_images_for(collection_pk)
        .select_related("license")
        .order_by("pk")
    )


def _neighbours(collection_pk, page_ids):
    """Map each id on the page to its ``(previous, next)`` sibling.

    Two extra indexed lookups pick up the siblings that sit just outside the
    page, so the viewer can walk across a page boundary.
    """
    if not page_ids:
        return {}
    base = _ordered_items(collection_pk).values_list("pk", flat=True)
    before = base.filter(pk__lt=page_ids[0]).order_by("-pk").first()
    after = base.filter(pk__gt=page_ids[-1]).order_by("pk").first()
    sequence = [before, *page_ids, after]
    return {
        image_id: (sequence[index - 1], sequence[index + 1])
        for index, image_id in enumerate(sequence)
        if index not in (0, len(sequence) - 1) and image_id is not None
    }


@require_GET
def items(request, collection_uuid):
    row = _row_or_404(collection_uuid)
    limit = conf.clamp_limit(request.GET.get("limit"))

    queryset = _ordered_items(row.collection_pk)
    try:
        after = int(request.GET.get("page", ""))
    except (TypeError, ValueError):
        after = None
    if after is not None:
        queryset = queryset.filter(pk__gt=after)

    page = list(queryset[: limit + 1])
    has_more, page = len(page) > limit, page[:limit]

    neighbours = _neighbours(row.collection_pk, [image.pk for image in page])
    features = [
        stac.item_document(
            image,
            request,
            collection_uuid=str(row.uuid),
            neighbours=neighbours.get(image.pk, (None, None)),
        )
        for image in page
    ]

    links = [
        {
            "rel": "root",
            "type": "application/json",
            "href": request.build_absolute_uri(reverse("panoramax:landing")),
        },
        {
            "rel": "self",
            "type": GEOJSON,
            "href": request.build_absolute_uri(),
        },
        {
            "rel": "collection",
            "type": "application/json",
            "href": request.build_absolute_uri(
                reverse("panoramax:collection", args=[str(row.uuid)])
            ),
        },
    ]
    if has_more and page:
        links.append(
            {
                "rel": "next",
                "type": GEOJSON,
                "href": _with_query(
                    request,
                    reverse("panoramax:items", args=[str(row.uuid)]),
                    limit=limit,
                    page=page[-1].pk,
                ),
            }
        )
    return _json(
        {"type": "FeatureCollection", "features": features, "links": links},
        content_type=GEOJSON,
    )


@require_GET
def item(request, collection_uuid, item_uuid):
    row = _row_or_404(collection_uuid)
    try:
        image_pk = ids.decode_kind(item_uuid, ids.IMAGE)
    except ids.InvalidFederatedId:
        raise Http404("unknown item") from None

    image = _ordered_items(row.collection_pk).filter(pk=image_pk).first()
    if image is None:
        raise Http404("unknown item")

    neighbours = _neighbours(row.collection_pk, [image.pk]).get(image.pk, (None, None))
    return _json(
        stac.item_document(
            image,
            request,
            collection_uuid=str(row.uuid),
            neighbours=neighbours,
        ),
        content_type=GEOJSON,
    )


# --------------------------------------------------------------------------
# Item search
# --------------------------------------------------------------------------


def _bbox_filter(queryset, raw):
    try:
        west, south, east, north = (float(value) for value in raw.split(","))
    except (AttributeError, TypeError, ValueError):
        return queryset
    box = Polygon.from_bbox((west, south, east, north))
    # The join hits the spatial index on images_georeference.point and prunes
    # cheaply; the annotation check is the exact one, since only the *latest*
    # georeference decides where an item is published.
    return (
        queryset.filter(georeferences__point__within=box)
        .filter(geo_point__within=box)
        .distinct()
    )


def _datetime_filter(queryset, raw):
    """Year-granular temporal search.

    An image's interval only exists once EDTF has been parsed in Python; the
    database holds the bounding years (``start_decdate`` / ``end_decdate``), so
    that is the resolution search operates at. Interval-overlap semantics, so
    an open bound on either side behaves as STAC expects.
    """
    if not raw:
        return queryset
    start, _, end = raw.partition("/")
    if not _:
        end = start

    def year_of(value):
        value = value.strip()
        if not value or value == "..":
            return None
        try:
            return int(value[:4])
        except ValueError:
            return None

    lower, upper = year_of(start), year_of(end)
    if lower is not None:
        queryset = queryset.filter(end_decdate__gte=lower)
    if upper is not None:
        queryset = queryset.filter(start_decdate__lte=upper)
    return queryset


@require_GET
def search(request):
    limit = conf.clamp_limit(request.GET.get("limit"))
    queryset = queries.federatable_images().select_related("license", "collection")

    if request.GET.get("bbox"):
        queryset = _bbox_filter(queryset, request.GET["bbox"])
    queryset = _datetime_filter(queryset, request.GET.get("datetime"))

    if request.GET.get("collections"):
        wanted = []
        for value in request.GET["collections"].split(","):
            try:
                wanted.append(ids.decode_kind(value.strip(), ids.COLLECTION))
            except ids.InvalidFederatedId:
                continue
        queryset = queryset.filter(collection_id__in=wanted)

    if request.GET.get("ids"):
        wanted = []
        for value in request.GET["ids"].split(","):
            try:
                wanted.append(ids.decode_kind(value.strip(), ids.IMAGE))
            except ids.InvalidFederatedId:
                continue
        queryset = queryset.filter(pk__in=wanted)

    queryset = queryset.order_by("pk")
    try:
        after = int(request.GET.get("page", ""))
    except (TypeError, ValueError):
        after = None
    if after is not None:
        queryset = queryset.filter(pk__gt=after)

    page = list(queryset[: limit + 1])
    has_more, page = len(page) > limit, page[:limit]

    features = [
        stac.item_document(
            image,
            request,
            collection_uuid=str(ids.collection_uuid(image.collection_id)),
        )
        for image in page
    ]
    links = [
        {
            "rel": "root",
            "type": "application/json",
            "href": request.build_absolute_uri(reverse("panoramax:landing")),
        },
        {"rel": "self", "type": GEOJSON, "href": request.build_absolute_uri()},
    ]
    if has_more and page:
        params = {
            key: request.GET[key]
            for key in ("bbox", "datetime", "collections", "ids")
            if request.GET.get(key)
        }
        links.append(
            {
                "rel": "next",
                "type": GEOJSON,
                "href": _with_query(
                    request,
                    reverse("panoramax:search"),
                    limit=limit,
                    page=page[-1].pk,
                    **params,
                ),
            }
        )
    return _json(
        {
            "type": "FeatureCollection",
            "features": features,
            "links": links,
        },
        content_type=GEOJSON,
    )


# --------------------------------------------------------------------------
# Previews and map tiles
# --------------------------------------------------------------------------


@require_GET
def picture_thumbnail(request, item_uuid):
    """``rel="item-preview"``: redirect to wherever the thumbnail really lives."""
    try:
        image_pk = ids.decode_kind(item_uuid, ids.IMAGE)
    except ids.InvalidFederatedId:
        raise Http404("unknown item") from None
    image = queries.federatable_images().filter(pk=image_pk).first()
    if image is None:
        raise Http404("unknown item")
    return redirect(image.thumbnail or image.display_permalink)


@require_GET
def collection_thumbnail(request, collection_uuid):
    """``rel="collection-preview"``: the first published picture's thumbnail."""
    row = _row_or_404(collection_uuid)
    image = _ordered_items(row.collection_pk).first()
    if image is None:
        raise Http404("nothing published for this collection")
    return redirect(image.thumbnail or image.display_permalink)


@require_GET
def style(request):
    return _json(tiles.style_document(request))


@require_GET
def vector_tile(request, z, x, y):
    data = tiles.render(int(z), int(x), int(y))
    response = HttpResponse(data, content_type="application/vnd.mapbox-vector-tile")
    response["Cache-Control"] = CACHE_CONTROL
    return response
