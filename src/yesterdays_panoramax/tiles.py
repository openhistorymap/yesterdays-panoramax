"""Vector tiles for the Panoramax web viewer.

The viewer expects three layers, and switches between them by zoom:

===========  ======  ==================================================
``grid``      z < 6   density cells, with ``nb_pictures`` and ``coef``
``sequences`` z < 15  one feature per collection, carrying ``id``
``pictures``  z >= 15 one feature per picture: ``id``, ``ts``, ``heading``
===========  ======  ==================================================

Panoramax draws ``sequences`` as lines, because one of its sequences is a walk
or a drive and its pictures fall along a path. A Yesterdays collection is an
archival album -- photographs scattered across a city over decades, in no
spatial order at all -- so joining them into a line would draw a route nobody
ever walked. This publishes each collection as a multipoint instead, and the
style served alongside draws it as points. The central catalogue builds its own
geometry from the harvested items regardless, so this choice only affects
viewers pointed straight at this instance.

The SQL repeats the eligibility rules from ``queries`` rather than calling
them, because a tile has to be one round trip. The two must be kept in step;
``test_tiles_match_the_api`` in ``tests.py`` fails if they drift.
"""

from django.db import connection

from . import conf, ids, stac

# Panoramax's own breakpoints, so a viewer configured for the federation
# behaves the same when pointed at this instance.
GRID_MAX_ZOOM = 6
PICTURES_MIN_ZOOM = 15

# Eligibility, in SQL. Mirrors panoramax.queries.federatable_images().
_ELIGIBLE = """
WITH latest AS (
    SELECT DISTINCT ON (g.image_id)
        g.image_id, g.point, g.direction
    FROM images_georeference g
    ORDER BY g.image_id, g.georeferenced_at DESC, g.id DESC
),
eligible AS (
    SELECT
        i.id,
        i.collection_id,
        i.start_decdate,
        ST_Transform(l.point, 3857) AS pt,
        l.direction
    FROM images_image i
    JOIN latest l ON l.image_id = i.id
    LEFT JOIN images_license lic ON lic.id = i.license_id
    WHERE i.is_searchable = true
      AND i.aerial = false
      AND i.will_not_georef = false
      AND i.edtf_date IS NOT NULL
      AND i.edtf_date <> ''
      AND i.permalink <> ''
      AND lower(lic.name) = ANY(%(licenses)s)
)
"""

# `id` must be the federated UUID, not the primary key, because the viewer
# uses it to fetch the item straight back out of the API. The nine-byte prefix
# is a constant for a given namespace and kind (see panoramax.ids), so it is
# computed in Python and the key is appended here: int8send gives eight
# big-endian bytes and the scheme uses the low seven.
_UUID = (
    "encode(%(prefix_{kind})s::bytea"
    " || substring(int8send({column}::bigint) from 2), 'hex')::uuid"
)

_PICTURES = f"""
SELECT ST_AsMVT(q, 'pictures') FROM (
    SELECT
        ST_AsMVTGeom(e.pt, ST_TileEnvelope(%(z)s, %(x)s, %(y)s)) AS geom,
        {_UUID.format(kind="image", column="e.id")} AS id,
        e.start_decdate AS ts,
        e.direction AS heading
    FROM eligible e
    WHERE e.pt && ST_TileEnvelope(%(z)s, %(x)s, %(y)s)
) q
"""

_SEQUENCES = f"""
SELECT ST_AsMVT(q, 'sequences') FROM (
    SELECT
        ST_AsMVTGeom(
            ST_Collect(e.pt), ST_TileEnvelope(%(z)s, %(x)s, %(y)s)
        ) AS geom,
        {_UUID.format(kind="collection", column="e.collection_id")} AS id,
        COUNT(*) AS nb_pictures
    FROM eligible e
    WHERE e.pt && ST_TileEnvelope(%(z)s, %(x)s, %(y)s)
    GROUP BY e.collection_id
) q
"""

# One cell per 1/64th of the tile, which is what keeps a world view legible
# without shipping a point per photograph.
_GRID = """
SELECT ST_AsMVT(q, 'grid') FROM (
    SELECT
        ST_AsMVTGeom(cell, ST_TileEnvelope(%(z)s, %(x)s, %(y)s)) AS geom,
        row_number() OVER (ORDER BY cell) AS id,
        nb_pictures,
        nb_pictures::float / GREATEST(MAX(nb_pictures) OVER (), 1) AS coef
    FROM (
        SELECT
            ST_Centroid(ST_Collect(e.pt)) AS cell,
            COUNT(*) AS nb_pictures
        FROM eligible e
        WHERE e.pt && ST_TileEnvelope(%(z)s, %(x)s, %(y)s)
        GROUP BY ST_SnapToGrid(
            e.pt,
            (ST_XMax(ST_TileEnvelope(%(z)s, %(x)s, %(y)s))
             - ST_XMin(ST_TileEnvelope(%(z)s, %(x)s, %(y)s))) / 8.0
        )
    ) cells
) q
"""


def _layers_for(zoom):
    """Which layers a tile at *zoom* carries."""
    layers = []
    if zoom < GRID_MAX_ZOOM:
        layers.append(_GRID)
    if zoom < PICTURES_MIN_ZOOM:
        layers.append(_SEQUENCES)
    if zoom >= PICTURES_MIN_ZOOM:
        layers.append(_PICTURES)
    return layers


def render(z, x, y) -> bytes:
    """Build the MVT for one tile. Returns empty bytes for an empty tile."""
    allowed = conf.license_allowlist()
    if not conf.enabled() or not allowed:
        return b""

    params = {
        "z": z,
        "x": x,
        "y": y,
        "licenses": list(allowed),
        "prefix_image": ids.prefix_bytes(ids.IMAGE),
        "prefix_collection": ids.prefix_bytes(ids.COLLECTION),
    }

    payload = b""
    with connection.cursor() as cursor:
        for layer_sql in _layers_for(z):
            cursor.execute(_ELIGIBLE + layer_sql, params)
            row = cursor.fetchone()
            if row and row[0]:
                # MVT is a protobuf of repeated layer messages, so tiles
                # concatenate: appending one layer's bytes to another's yields
                # a valid tile carrying both.
                payload += bytes(row[0])
    return payload


def style_document(request):
    """A MapLibre style advertising this instance's tiles.

    Linked from the landing page as ``rel="xyz-style"``, which is how the
    Panoramax viewer discovers a third-party instance's tiles.
    """
    tile_url = stac.tile_template(request)
    return {
        "version": 8,
        "name": conf.instance_name(),
        "sources": {
            "panoramax": {
                "type": "vector",
                "tiles": [tile_url],
                "minzoom": 0,
                "maxzoom": 18,
            }
        },
        "layers": [
            {
                "id": "panoramax_grid",
                "type": "circle",
                "source": "panoramax",
                "source-layer": "grid",
                "maxzoom": GRID_MAX_ZOOM,
                "paint": {
                    "circle-color": conf.color(),
                    "circle-opacity": 0.7,
                    "circle-radius": [
                        "interpolate",
                        ["linear"],
                        ["get", "coef"],
                        0,
                        3,
                        1,
                        18,
                    ],
                },
            },
            {
                "id": "panoramax_sequences",
                "type": "circle",
                "source": "panoramax",
                "source-layer": "sequences",
                "minzoom": GRID_MAX_ZOOM,
                "maxzoom": PICTURES_MIN_ZOOM,
                "paint": {
                    "circle-color": conf.color(),
                    "circle-opacity": 0.8,
                    "circle-radius": 3,
                },
            },
            {
                "id": "panoramax_pictures",
                "type": "circle",
                "source": "panoramax",
                "source-layer": "pictures",
                "minzoom": PICTURES_MIN_ZOOM,
                "paint": {
                    "circle-color": conf.color(),
                    "circle-stroke-color": "#ffffff",
                    "circle-stroke-width": 1,
                    "circle-radius": 6,
                },
            },
        ],
    }
