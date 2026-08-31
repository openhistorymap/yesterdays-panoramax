"""URL routing for the federation endpoints.

These must be mounted at ``/api/`` exactly. The harvester builds its requests
as ``{instance_url}/api/collections`` and ``{instance_url}/api/configuration``
with the prefix hardcoded, so mounting the app anywhere else makes the instance
unharvestable. Include it *after* ``api/v2/`` in the root URLconf so the
existing REST API keeps its routes.
"""

from django.urls import path, re_path

from . import views

app_name = "panoramax"

# UUIDs are matched loosely rather than with Django's `uuid` converter: the
# converter rejects a malformed value with a 404 from the resolver, which hides
# the difference between "not a UUID" and "not ours". Both end up as 404s, but
# routing them through the view keeps that decision in one place.
UUID = r"[0-9a-fA-F-]{36}"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("configuration", views.configuration, name="configuration"),
    path("search", views.search, name="search"),
    # Ahead of the <uuid> route, which would otherwise swallow "queryables".
    path("collections/queryables", views.queryables, name="queryables"),
    path("collections", views.collections, name="collections"),
    re_path(
        rf"^collections/(?P<collection_uuid>{UUID})$",
        views.collection,
        name="collection",
    ),
    re_path(
        rf"^collections/(?P<collection_uuid>{UUID})/items$",
        views.items,
        name="items",
    ),
    re_path(
        rf"^collections/(?P<collection_uuid>{UUID})/items/(?P<item_uuid>{UUID})$",
        views.item,
        name="item",
    ),
    re_path(
        rf"^collections/(?P<collection_uuid>{UUID})/thumb\.jpg$",
        views.collection_thumbnail,
        name="collection-thumbnail",
    ),
    re_path(
        rf"^pictures/(?P<item_uuid>{UUID})/thumb\.jpg$",
        views.picture_thumbnail,
        name="picture-thumbnail",
    ),
    path("map/style.json", views.style, name="style"),
    path("map/<int:z>/<int:x>/<int:y>.mvt", views.vector_tile, name="tile"),
]
