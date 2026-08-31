"""Tests for the Panoramax federation adapter.

The contract these protect is not a written specification -- it is the
meta-catalogue's harvester and database schema. Anything asserted here about
what the federation "requires" was read off
``gitlab.com/panoramax/server/meta-catalog`` (``harvester/harvester/harvest.py``
and ``migrations/sql/``), because the harvester reads our JSON and the docs do
not.
"""

import uuid

from django.contrib.gis.geos import Point
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from tests.images.models import Collection, Georeference, Image, License, Source
from yesterdays_panoramax import api, conf, dates, filters, ids
from yesterdays_panoramax.decisions import EXCLUDE, INCLUDE, ImageDecision
from yesterdays_panoramax.models import PublishedCollection

FEDERATED = {
    "PANORAMAX_ENABLED": True,
    "PANORAMAX_LICENSE_ALLOWLIST": {"Public Domain": "CC0-1.0"},
    "PANORAMAX_INSTANCE_NAME": "Yesterdays Test",
}


class FederatedIdTests(TestCase):
    """The catalogue casts our ids straight to UUID columns, so they must be
    real UUIDs -- and we must be able to get back from one to a primary key
    without a lookup table, because this app adds no column to `images`."""

    def test_round_trips_for_every_kind(self):
        for kind in ids.KINDS:
            for pk in (1, 42, 10**6, ids.MAX_PK):
                with self.subTest(kind=kind, pk=pk):
                    self.assertEqual(ids.decode(ids.encode(kind, pk)), (kind, pk))

    def test_is_a_well_formed_uuid(self):
        value = ids.image_uuid(42)
        self.assertIsInstance(value, uuid.UUID)
        self.assertEqual(value.version, 8)
        self.assertEqual(value.bytes[8] >> 6, 0b10, "RFC 9562 variant bits")

    def test_is_deterministic(self):
        self.assertEqual(ids.image_uuid(7), ids.image_uuid(7))

    def test_kinds_do_not_collide(self):
        self.assertNotEqual(ids.image_uuid(42), ids.collection_uuid(42))

    def test_rejects_foreign_uuids(self):
        with self.assertRaises(ids.InvalidFederatedId):
            ids.decode(uuid.uuid4())

    def test_rejects_another_namespace(self):
        minted = ids.image_uuid(42)
        with override_settings(PANORAMAX_UUID_NAMESPACE=uuid.UUID(int=99)):
            with self.assertRaises(ids.InvalidFederatedId):
                ids.decode(minted)

    def test_wrong_kind_is_rejected(self):
        with self.assertRaises(ids.InvalidFederatedId):
            ids.decode_kind(ids.collection_uuid(1), ids.IMAGE)

    def test_sql_prefix_matches_python(self):
        """The tiles mint ids in SQL by appending a key to this prefix."""
        for kind in ids.KINDS:
            self.assertEqual(ids.encode(kind, 42).bytes[:9], ids.prefix_bytes(kind))


class EdtfDateTests(TestCase):
    """The catalogue's `datetime` column is NOT NULL, but Yesterdays dates are
    EDTF and frequently ranges."""

    def test_exact_date_is_an_instant(self):
        start, end = dates.edtf_interval("1901-06-15")
        self.assertEqual(dates.rfc3339(start), "1901-06-15T00:00:00Z")
        self.assertTrue(start <= end)

    def test_a_year_is_a_range(self):
        start, end = dates.edtf_interval("1890")
        self.assertEqual(start.year, 1890)
        self.assertEqual(end.year, 1890)
        self.assertFalse(dates.is_instant(start, end))

    def test_decade_spans_ten_years(self):
        start, end = dates.edtf_interval("189X")
        self.assertEqual(start.year, 1890)
        self.assertEqual(end.year, 1899)

    def test_unparseable_is_not_published(self):
        self.assertEqual(dates.edtf_interval("not a date"), (None, None))
        self.assertEqual(dates.edtf_interval(None), (None, None))
        self.assertEqual(dates.edtf_interval(""), (None, None))


class FilterParsingTests(TestCase):
    """The harvester sends exactly one filter expression; anything else must
    widen the result set rather than fail the harvest."""

    HARVESTER = "status IN ('deleted','ready') AND updated > '2026-08-30T07:00:00Z'"

    def test_parses_the_harvester_expression(self):
        parsed = filters.parse(self.HARVESTER)
        self.assertEqual(parsed.statuses, {"deleted", "ready"})
        self.assertTrue(parsed.wants_ready)
        self.assertTrue(parsed.wants_deleted)
        self.assertEqual(parsed.updated_after.year, 2026)
        self.assertFalse(parsed.updated_after_inclusive)

    def test_empty_filter_wants_the_live_catalogue(self):
        """No status clause means a browser, or a first crawl: live rows only.
        Tombstones are only ever interesting to an incremental harvest, and
        that always names them explicitly."""
        parsed = filters.parse("")
        self.assertTrue(parsed.wants_ready)
        self.assertFalse(parsed.wants_deleted)
        self.assertIsNone(parsed.updated_after)

    def test_unknown_clause_is_ignored_not_rejected(self):
        parsed = filters.parse("updated > '2026-01-01' AND wibble = 'x'")
        self.assertEqual(parsed.updated_after.year, 2026)

    def test_unparseable_timestamp_is_ignored(self):
        self.assertIsNone(filters.parse("updated > 'soon'").updated_after)


class FederationTestCase(TestCase):
    """Shared fixture: one public source, one public collection, one dated,
    licensed, georeferenced image."""

    def setUp(self):
        self.license = License.objects.create(
            name="Public Domain", display_name="Public Domain"
        )
        self.other_license = License.objects.create(
            name="All Rights Reserved", display_name="All Rights Reserved"
        )
        self.source = Source.objects.create(
            name="City Archive",
            slug="city-archive",
            url="https://archive.example",
            description="",
        )
        self.collection = Collection.objects.create(
            source=self.source, name="Downtown", slug="downtown"
        )

    def make_image(self, **kwargs):
        options = {
            "collection": self.collection,
            "title": "Main Street",
            "permalink": "https://cdn.example/main.jpg",
            "thumbnail": "https://cdn.example/main-thumb.webp",
            "edtf_date": "1890",
            "license": self.license,
            "width": 1000,
            "height": 800,
        }
        options.update(kwargs)
        return Image.objects.create(**options)

    def georeference(self, image, **kwargs):
        options = {
            "image": image,
            "point": Point(-77.436, 37.541, srid=4326),
            "direction": 90,
            "confidence": "high",
        }
        options.update(kwargs)
        return Georeference.objects.create(**options)

    def publish(self):
        """Create a georeferenced image and refresh federation state."""
        image = self.make_image()
        self.georeference(image)
        PublishedCollection.refresh(self.collection.pk)
        return image


@override_settings(**FEDERATED)
class EligibilityTests(FederationTestCase):
    def test_publishes_a_georeferenced_licensed_dated_image(self):
        self.publish()
        row = PublishedCollection.objects.get(collection_pk=self.collection.pk)
        self.assertTrue(row.published)
        self.assertEqual(row.item_count, 1)
        self.assertEqual(row.license_label, "CC0-1.0")

    def test_an_image_without_a_georeference_is_not_published(self):
        self.make_image()
        PublishedCollection.refresh(self.collection.pk)
        self.assertFalse(PublishedCollection.objects.exists())

    def test_a_disallowed_licence_is_not_published(self):
        image = self.make_image(license=self.other_license)
        self.georeference(image)
        PublishedCollection.refresh(self.collection.pk)
        self.assertFalse(PublishedCollection.objects.exists())

    def test_an_undated_image_is_not_published(self):
        image = self.make_image(edtf_date=None)
        self.georeference(image)
        PublishedCollection.refresh(self.collection.pk)
        self.assertFalse(PublishedCollection.objects.exists())

    def test_an_aerial_is_not_published(self):
        image = self.make_image(aerial=True)
        self.georeference(image)
        PublishedCollection.refresh(self.collection.pk)
        self.assertFalse(PublishedCollection.objects.exists())

    def test_nothing_is_published_without_an_allowlist(self):
        with override_settings(PANORAMAX_LICENSE_ALLOWLIST={}):
            self.publish()
        self.assertFalse(PublishedCollection.objects.exists())

    def test_nothing_is_published_when_disabled(self):
        with override_settings(PANORAMAX_ENABLED=False):
            self.publish()
        self.assertFalse(PublishedCollection.objects.exists())

    def test_the_latest_georeference_wins(self):
        """The same rule the site's own map uses, so the federation and the
        site never disagree about where a photograph is."""
        image = self.make_image()
        self.georeference(image, point=Point(-1.0, 1.0, srid=4326))
        self.georeference(image, point=Point(-2.0, 2.0, srid=4326), direction=180)
        PublishedCollection.refresh(self.collection.pk)
        row = PublishedCollection.objects.get()
        self.assertAlmostEqual(row.min_x, -2.0)
        self.assertAlmostEqual(row.min_y, 2.0)


@override_settings(**FEDERATED)
class ChangePropagationTests(FederationTestCase):
    """The harvester filters on the *collection's* `updated` and then re-fetches
    that collection's items. A change beneath a collection that does not move
    `updated` never reaches the federation at all."""

    def test_a_new_georeference_bumps_the_collection(self):
        self.publish()
        before = PublishedCollection.objects.get().updated

        second = self.make_image(title="Second Street")
        with self.captureOnCommitCallbacks(execute=True):
            self.georeference(second)

        row = PublishedCollection.objects.get()
        self.assertGreater(row.updated, before)
        self.assertEqual(row.item_count, 2)

    def test_making_a_collection_private_leaves_a_tombstone(self):
        self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            self.collection.public = False
            self.collection.save()

        row = PublishedCollection.objects.get()
        self.assertFalse(row.published)
        self.assertIsNotNone(row.unpublished_at)
        self.assertTrue(row.is_tombstone)

    def test_making_a_source_private_withdraws_its_collections(self):
        self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            self.source.public = False
            self.source.save()

        self.assertFalse(PublishedCollection.objects.get().published)

    def test_backfill_does_not_touch_unchanged_collections(self):
        """A reconcile must not look like a site-wide edit, or every harvest
        re-crawls the entire catalogue."""
        self.publish()
        before = PublishedCollection.objects.get().updated
        PublishedCollection.refresh(self.collection.pk, touch=False)
        self.assertEqual(PublishedCollection.objects.get().updated, before)


@override_settings(**FEDERATED)
class HarvestContractTests(FederationTestCase):
    """The four requests the harvester actually makes."""

    def test_configuration_is_served(self):
        response = self.client.get(reverse("panoramax:configuration"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"]["label"], "Yesterdays Test")
        self.assertIn("id", body["license"])

    def test_landing_advertises_the_catalogue(self):
        body = self.client.get(reverse("panoramax:landing")).json()
        self.assertEqual(body["type"], "Catalog")
        rels = {link["rel"] for link in body["links"]}
        self.assertIn("data", rels)
        self.assertIn("search", rels)

    def test_queryables_advertise_what_the_filter_uses(self):
        body = self.client.get(reverse("panoramax:queryables")).json()
        self.assertEqual(set(body["properties"]), {"created", "updated"})

    def test_collections_listing_shape(self):
        self.publish()
        body = self.client.get(reverse("panoramax:collections")).json()
        self.assertEqual(len(body["collections"]), 1)

        collection = body["collections"][0]
        # The catalogue generates its primary key as (content->>'id')::UUID.
        uuid.UUID(collection["id"])
        self.assertEqual(collection["type"], "Collection")
        self.assertIn("created", collection)
        self.assertIn("updated", collection)
        self.assertIn("extent", collection)
        # get_items() builds its URL from the collection's rel=self href.
        self_href = next(
            link["href"] for link in collection["links"] if link["rel"] == "self"
        )
        self.assertTrue(self_href.startswith("http"))

    def test_incremental_filter_narrows_the_listing(self):
        self.publish()
        row = PublishedCollection.objects.get()
        after = row.updated.isoformat().replace("+00:00", "Z")
        expression = f"status IN ('deleted','ready') AND updated > '{after}'"

        body = self.client.get(
            reverse("panoramax:collections"), {"filter": expression}
        ).json()
        self.assertEqual(body["collections"], [])

    def test_a_withdrawn_collection_is_published_as_deleted(self):
        """`geovisio:status: "deleted"` is the only thing that removes a
        collection from the federation."""
        self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            self.collection.public = False
            self.collection.save()

        # An incremental harvest is the only caller that asks for tombstones.
        body = self.client.get(
            reverse("panoramax:collections"),
            {"filter": "status IN ('deleted','ready') AND updated > '2000-01-01'"},
        ).json()
        self.assertEqual(len(body["collections"]), 1)
        self.assertEqual(body["collections"][0]["geovisio:status"], "deleted")

    def test_an_unfiltered_listing_hides_tombstones(self):
        """A browser asking for the catalogue wants what is published."""
        self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            self.collection.public = False
            self.collection.save()

        body = self.client.get(reverse("panoramax:collections")).json()
        self.assertEqual(body["collections"], [])

    def test_next_link_survives_the_harvester_filter(self):
        """The harvester echoes our `next` href back verbatim, and the filter
        it carries is full of spaces and quotes."""
        self.publish()
        other = Collection.objects.create(
            source=self.source, name="Uptown", slug="uptown"
        )
        self.georeference(self.make_image(collection=other))
        PublishedCollection.refresh(other.pk)

        expression = "status IN ('deleted','ready') AND updated > '2000-01-01'"
        body = self.client.get(
            reverse("panoramax:collections"),
            {"limit": 1, "filter": expression},
        ).json()
        next_href = next(
            link["href"] for link in body["links"] if link["rel"] == "next"
        )
        self.assertNotIn(" ", next_href)

        second = self.client.get(next_href).json()
        self.assertEqual(len(second["collections"]), 1)
        self.assertNotEqual(
            body["collections"][0]["id"], second["collections"][0]["id"]
        )

    def test_listing_paginates_with_a_next_link(self):
        self.publish()
        other = Collection.objects.create(
            source=self.source, name="Uptown", slug="uptown"
        )
        image = self.make_image(collection=other)
        self.georeference(image)
        PublishedCollection.refresh(other.pk)

        body = self.client.get(reverse("panoramax:collections"), {"limit": 1}).json()
        self.assertEqual(len(body["collections"]), 1)
        next_href = next(
            link["href"] for link in body["links"] if link["rel"] == "next"
        )

        second = self.client.get(next_href).json()
        self.assertEqual(len(second["collections"]), 1)
        self.assertNotEqual(
            body["collections"][0]["id"], second["collections"][0]["id"]
        )


@override_settings(**FEDERATED)
class ItemTests(FederationTestCase):
    def setUp(self):
        super().setUp()
        self.image = self.publish()
        self.row = PublishedCollection.objects.get()

    def items(self):
        return self.client.get(
            reverse("panoramax:items", args=[str(self.row.uuid)])
        ).json()

    def test_item_satisfies_the_catalogue_schema(self):
        feature = self.items()["features"][0]
        # items.id, items.collection_id: both cast to UUID by the catalogue.
        uuid.UUID(feature["id"])
        uuid.UUID(feature["collection"])
        # items.geometry: ST_GeomFromGeoJSON(content->'geometry')
        self.assertEqual(feature["geometry"]["type"], "Point")
        # items.datetime: TIMESTAMPTZ NOT NULL
        self.assertIsNotNone(feature["properties"]["datetime"])

    def test_item_carries_the_azimuth_and_dimensions(self):
        properties = self.items()["features"][0]["properties"]
        self.assertEqual(properties["view:azimuth"], 90)
        self.assertEqual(
            properties["pers:interior_orientation"]["sensor_array_dimensions"],
            [1000, 800],
        )

    def test_a_quarter_turn_swaps_the_published_dimensions(self):
        """`hd` serves the transformed rendition, so its dimensions are the
        rotated ones."""
        self.image.rotation = 90
        self.image.save()
        properties = self.items()["features"][0]["properties"]
        self.assertEqual(
            properties["pers:interior_orientation"]["sensor_array_dimensions"],
            [800, 1000],
        )

    def test_flat_pictures_declare_no_field_of_view(self):
        """`field_of_view == 360` is what the catalogue keys on to file a
        picture as equirectangular."""
        orientation = self.items()["features"][0]["properties"][
            "pers:interior_orientation"
        ]
        self.assertNotIn("field_of_view", orientation)

    def test_assets_cover_the_three_roles_the_viewer_needs(self):
        assets = self.items()["features"][0]["assets"]
        self.assertEqual(assets["hd"]["roles"], ["data"])
        self.assertEqual(assets["sd"]["roles"], ["visual"])
        self.assertEqual(assets["thumb"]["roles"], ["thumbnail"])
        for asset in assets.values():
            self.assertIn(asset["type"], {"image/jpeg", "image/webp"})

    def test_a_ranged_date_publishes_start_and_end(self):
        properties = self.items()["features"][0]["properties"]
        self.assertIn("start_datetime", properties)
        self.assertIn("end_datetime", properties)
        self.assertEqual(properties["datetime"], properties["start_datetime"])

    def test_item_links_back_to_yesterdays(self):
        """`via` survives harvesting, so the federation keeps a route home."""
        links = self.items()["features"][0]["links"]
        via = next(link for link in links if link["rel"] == "via")
        self.assertIn(str(self.image.pk), via["href"])

    def test_single_item_endpoint(self):
        item_uuid = ids.image_uuid(self.image.pk)
        response = self.client.get(
            reverse("panoramax:item", args=[str(self.row.uuid), str(item_uuid)])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(item_uuid))

    def test_a_foreign_uuid_is_a_404(self):
        response = self.client.get(
            reverse("panoramax:collection", args=[str(uuid.uuid4())])
        )
        self.assertEqual(response.status_code, 404)


@override_settings(**FEDERATED)
class SearchTests(FederationTestCase):
    def setUp(self):
        super().setUp()
        self.publish()

    def test_search_returns_a_feature_collection(self):
        body = self.client.get(reverse("panoramax:search")).json()
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual(len(body["features"]), 1)

    def test_bbox_excludes_what_is_outside_it(self):
        body = self.client.get(
            reverse("panoramax:search"), {"bbox": "10,10,11,11"}
        ).json()
        self.assertEqual(body["features"], [])

    def test_bbox_includes_what_is_inside_it(self):
        body = self.client.get(
            reverse("panoramax:search"), {"bbox": "-78,37,-77,38"}
        ).json()
        self.assertEqual(len(body["features"]), 1)

    def test_datetime_filters_by_year(self):
        self.assertEqual(
            self.client.get(
                reverse("panoramax:search"), {"datetime": "1950/1960"}
            ).json()["features"],
            [],
        )
        self.assertEqual(
            len(
                self.client.get(
                    reverse("panoramax:search"), {"datetime": "1880/1900"}
                ).json()["features"]
            ),
            1,
        )


class DisabledInstanceTests(FederationTestCase):
    """An unconfigured install must answer, and publish nothing. A 404 sends an
    operator hunting for a broken deployment; an empty catalogue is true."""

    def test_endpoints_answer_when_disabled(self):
        for name in ("landing", "configuration", "collections", "search"):
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(f"panoramax:{name}"))
                self.assertEqual(response.status_code, 200)

    def test_catalogue_is_empty_when_disabled(self):
        self.publish()
        body = self.client.get(reverse("panoramax:collections")).json()
        self.assertEqual(body["collections"], [])


@override_settings(**FEDERATED)
class VectorTileTests(FederationTestCase):
    """The viewer discovers these through the landing page's xyz-style link."""

    def setUp(self):
        super().setUp()
        self.publish()

    def test_style_advertises_the_three_layers(self):
        body = self.client.get(reverse("panoramax:style")).json()
        self.assertEqual(body["version"], 8)
        layers = {layer["source-layer"] for layer in body["layers"]}
        self.assertEqual(layers, {"grid", "sequences", "pictures"})

    def test_a_picture_zoom_tile_renders(self):
        response = self.client.get(reverse("panoramax:tile", args=[16, 18752, 25073]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.mapbox-vector-tile")

    def test_every_zoom_band_renders(self):
        """Each band runs different SQL; a broken one must not 500."""
        for z, x, y in ((2, 1, 1), (10, 292, 391), (16, 18752, 25073)):
            with self.subTest(zoom=z):
                self.assertEqual(
                    self.client.get(
                        reverse("panoramax:tile", args=[z, x, y])
                    ).status_code,
                    200,
                )

    def test_tiles_are_empty_when_disabled(self):
        with override_settings(PANORAMAX_ENABLED=False):
            response = self.client.get(
                reverse("panoramax:tile", args=[16, 18752, 25073])
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")


@override_settings(**FEDERATED)
class ImageDecisionTests(FederationTestCase):
    """Per-image federation control.

    The feature has to be inert until used: an installation that never rules on
    anything must behave exactly as it did before the model existed.
    """

    def published_ids(self):
        body = self.client.get(reverse("panoramax:search")).json()
        return {
            feature["properties"]["yesterdays:image_id"] for feature in body["features"]
        }

    # -- opt-out (the default) ------------------------------------------------

    def test_an_image_with_no_ruling_is_unaffected(self):
        """Django's exclude() across a nullable reverse relation must keep the
        rows that have no related object at all."""
        image = self.publish()
        self.assertEqual(self.published_ids(), {image.pk})

    def test_excluding_holds_an_image_back(self):
        image = self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            api.exclude_image(image, reason="Depicted person objected")
        self.assertEqual(self.published_ids(), set())

    def test_only_the_excluded_image_is_held_back(self):
        kept = self.publish()
        dropped = self.make_image(title="Second Street")
        self.georeference(dropped)
        with self.captureOnCommitCallbacks(execute=True):
            api.exclude_image(dropped)
        self.assertEqual(self.published_ids(), {kept.pk})

    def test_clearing_restores_an_image(self):
        image = self.publish()
        api.exclude_image(image)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(api.clear_decision(image))
        self.assertEqual(self.published_ids(), {image.pk})

    def test_approving_under_opt_out_records_without_changing_anything(self):
        image = self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            api.include_image(image, reason="Reviewed by the archivist")
        self.assertEqual(api.decision_for(image), INCLUDE)
        self.assertEqual(self.published_ids(), {image.pk})

    # -- opt-in ---------------------------------------------------------------

    def test_opt_in_publishes_nothing_until_approved(self):
        image = self.publish()
        with override_settings(PANORAMAX_IMAGE_POLICY=conf.OPT_IN):
            self.assertEqual(self.published_ids(), set())
            with self.captureOnCommitCallbacks(execute=True):
                api.include_image(image)
            self.assertEqual(self.published_ids(), {image.pk})

    def test_approval_does_not_override_the_licence_gate(self):
        """The licence gate is a legal control, not a default. A human ticking
        a box must not be able to walk past it."""
        image = self.make_image(license=self.other_license)
        self.georeference(image)
        api.include_image(image)
        with override_settings(PANORAMAX_IMAGE_POLICY=conf.OPT_IN):
            self.assertEqual(self.published_ids(), set())
        self.assertEqual(self.published_ids(), set())

    def test_approval_does_not_conjure_a_georeference(self):
        image = self.make_image()
        api.include_image(image)
        with override_settings(PANORAMAX_IMAGE_POLICY=conf.OPT_IN):
            self.assertFalse(api.is_published(image))

    def test_an_unknown_policy_is_refused(self):
        with override_settings(PANORAMAX_IMAGE_POLICY="opt-maybe"):
            with self.assertRaises(ImproperlyConfigured):
                conf.image_policy()

    # -- propagation ----------------------------------------------------------

    def test_a_ruling_bumps_the_collection(self):
        """Nothing in `images` is written, so without this the decision would
        sit in the database and never reach the federation."""
        image = self.publish()
        before = PublishedCollection.objects.get().updated
        with self.captureOnCommitCallbacks(execute=True):
            api.exclude_image(image)
        self.assertGreater(PublishedCollection.objects.get().updated, before)

    def test_excluding_the_last_image_tombstones_the_collection(self):
        image = self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            api.exclude_image(image)
        row = PublishedCollection.objects.get()
        self.assertFalse(row.published)
        self.assertTrue(row.is_tombstone)

    def test_an_excluded_image_leaves_the_item_listing(self):
        """Which is what removes it from the federation: the harvester replaces
        a collection's items wholesale on every pass."""
        kept = self.publish()
        dropped = self.make_image(title="Second Street")
        self.georeference(dropped)
        with self.captureOnCommitCallbacks(execute=True):
            api.exclude_image(dropped)

        row = PublishedCollection.objects.get()
        body = self.client.get(reverse("panoramax:items", args=[str(row.uuid)])).json()
        self.assertEqual(
            [f["properties"]["yesterdays:image_id"] for f in body["features"]],
            [kept.pk],
        )
        self.assertEqual(row.item_count, 1)

    # -- the model itself -----------------------------------------------------

    def test_is_published_reports_the_whole_test_not_just_the_ruling(self):
        image = self.publish()
        self.assertTrue(api.is_published(image))
        with self.captureOnCommitCallbacks(execute=True):
            api.exclude_image(image)
        self.assertFalse(api.is_published(image))

    def test_a_ruling_is_replaced_not_duplicated(self):
        image = self.publish()
        api.exclude_image(image, reason="first")
        api.include_image(image, reason="second")
        self.assertEqual(ImageDecision.objects.count(), 1)
        self.assertEqual(api.decision_for(image), INCLUDE)

    def test_deleting_an_image_takes_its_ruling_with_it(self):
        image = self.publish()
        api.exclude_image(image)
        with self.captureOnCommitCallbacks(execute=True):
            image.delete()
        self.assertEqual(ImageDecision.objects.count(), 0)

    def test_decision_for_is_none_when_nobody_has_ruled(self):
        image = self.publish()
        self.assertIsNone(api.decision_for(image))

    def test_helpers_accept_a_primary_key(self):
        image = self.publish()
        api.exclude_image(image.pk)
        self.assertEqual(api.decision_for(image.pk), EXCLUDE)
