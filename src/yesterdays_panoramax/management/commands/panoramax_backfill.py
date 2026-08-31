"""Bring federation state into line with the catalogue.

Needed in three situations:

* **First install.** Signals only see writes that happen after the app is
  added, so an existing archive has no federation state until this runs.
* **After bulk writes.** Imports that use ``bulk_create``/``update`` bypass
  Django's signals entirely, so anything they touched is invisible to the
  adapter.
* **After a settings change.** Widening ``PANORAMAX_LICENSE_ALLOWLIST``
  changes what is eligible without writing to any row, so nothing fires.

By default this does not move ``updated`` on collections whose published
content has not changed, so a routine reconcile does not look to the harvester
like a site-wide edit and force a re-crawl of the entire catalogue.
"""

from django.core.management.base import BaseCommand

from yesterdays_panoramax import conf, queries
from yesterdays_panoramax.models import PublishedCollection


class Command(BaseCommand):
    help = "Recompute Panoramax federation state for every collection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--touch",
            action="store_true",
            help=(
                "Bump `updated` on every collection, forcing the next harvest "
                "to re-crawl the whole catalogue. Only needed when the "
                "published representation itself has changed."
            ),
        )
        parser.add_argument(
            "--collection",
            type=int,
            action="append",
            dest="collections",
            help="Limit to this collection id. May be repeated.",
        )

    def handle(self, *args, **options):
        if not conf.enabled():
            self.stdout.write(
                self.style.WARNING(
                    "PANORAMAX_ENABLED is false: state will be recomputed, but "
                    "nothing is eligible, so every collection will be withdrawn."
                )
            )
        if not conf.license_allowlist():
            self.stdout.write(
                self.style.WARNING(
                    "PANORAMAX_LICENSE_ALLOWLIST is empty: no licence has been "
                    "approved for federation, so nothing will be published."
                )
            )

        targets = options.get("collections")
        if targets:
            collection_ids = sorted(set(targets))
        else:
            # Everything currently eligible, plus everything already on record
            # -- the latter so collections that have *become* ineligible get
            # tombstoned rather than quietly left published.
            eligible = set(queries.federatable_collection_ids())
            known = set(
                PublishedCollection.objects.values_list("collection_pk", flat=True)
            )
            collection_ids = sorted(eligible | known)

        published = withdrawn = untouched = 0
        for collection_id in collection_ids:
            row = PublishedCollection.refresh(collection_id, touch=options["touch"])
            if row is None:
                untouched += 1
            elif row.published:
                published += 1
            else:
                withdrawn += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{published} collection(s) published, {withdrawn} withdrawn, "
                f"{untouched} skipped."
            )
        )
        if withdrawn:
            self.stdout.write(
                "Withdrawn collections stay in the feed as tombstones until "
                "the federation has harvested their deletion."
            )
