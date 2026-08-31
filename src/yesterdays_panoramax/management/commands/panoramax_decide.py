"""Set or clear per-image federation decisions in bulk.

The admin is fine for ruling on one photograph. Curating an archive is not:
under ``PANORAMAX_IMAGE_POLICY = "opt-in"`` nothing is published until it is
approved, and approving ten thousand plates one at a time is not a workflow.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from yesterdays_panoramax import api, conf
from yesterdays_panoramax.decisions import EXCLUDE, INCLUDE, ImageDecision
from yesterdays_panoramax.hostmodels import Image


class Command(BaseCommand):
    help = "Include, exclude, or clear the federation decision on images."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=[INCLUDE, EXCLUDE, "clear"],
            help="Approve, hold back, or return images to the ordinary rules.",
        )
        parser.add_argument(
            "--image",
            type=int,
            action="append",
            dest="images",
            help="Image id. May be repeated.",
        )
        parser.add_argument(
            "--collection",
            type=int,
            action="append",
            dest="collections",
            help="Every image in this collection. May be repeated.",
        )
        parser.add_argument(
            "--reason",
            default="",
            help="Recorded against each ruling. Worth filling in.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change and stop.",
        )

    def handle(self, *args, **options):
        targets = self._targets(options)
        count = targets.count()
        action = options["action"]

        if not count:
            self.stdout.write(self.style.WARNING("No images matched."))
            return

        if options["dry_run"]:
            self.stdout.write(f"Would {action} {count} image(s). No changes made.")
            return

        if action == "clear":
            # One query, then one refresh per affected collection via signals.
            for pk in targets.values_list("pk", flat=True).iterator():
                api.clear_decision(pk)
        else:
            reason = options["reason"]
            for pk in targets.values_list("pk", flat=True).iterator():
                if action == INCLUDE:
                    api.include_image(pk, reason=reason)
                else:
                    api.exclude_image(pk, reason=reason)

        self.stdout.write(self.style.SUCCESS(f"{action}: {count} image(s)."))

        if action == INCLUDE and conf.image_policy() == conf.OPT_OUT:
            self.stdout.write(
                "Note: the policy is opt-out, where an image with no ruling is "
                "already publishable, so this recorded approval without "
                "changing what is published."
            )
        if action == EXCLUDE:
            self.stdout.write(
                "Excluded images leave the federation on the next harvest, "
                "which replaces each collection's items wholesale."
            )

    def _targets(self, options):
        images, collections = options.get("images"), options.get("collections")
        if not images and not collections:
            raise CommandError("Give at least one --image or --collection.")

        queryset = Image.objects.all()
        if options["action"] == "clear":
            # Only images that actually carry a ruling; the count should mean
            # "changed", not "considered".
            queryset = queryset.filter(
                pk__in=ImageDecision.objects.values_list("image_id", flat=True)
            )

        if images and collections:
            return queryset.filter(Q(pk__in=images) | Q(collection_id__in=collections))
        if images:
            return queryset.filter(pk__in=images)
        return queryset.filter(collection_id__in=collections)
