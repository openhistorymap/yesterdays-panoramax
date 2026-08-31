from django.apps import AppConfig


class PanoramaxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "yesterdays_panoramax"
    # Pinned, and not derived from `name`. The label decides table names
    # (`panoramax_publishedcollection`) and the URL namespace
    # (`reverse("panoramax:...")`). Letting it follow the distribution name
    # would rename the table under any installation that already has one.
    label = "panoramax"
    verbose_name = "Panoramax federation"

    def ready(self):
        # Registers the receivers that keep PublishedCollection in step with
        # the catalogue. Imported for the side effect only.
        from . import signals  # noqa: F401
