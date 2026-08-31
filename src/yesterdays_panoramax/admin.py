from django.contrib import admin

from .decisions import ImageDecision
from .models import PublishedCollection


@admin.register(PublishedCollection)
class PublishedCollectionAdmin(admin.ModelAdmin):
    """Read-only: every field is derived, and editing one would only be undone
    by the next refresh. Registered so operators can see what the federation
    has been told, and why a collection is or is not in it."""

    list_display = (
        "collection_pk",
        "collection",
        "published",
        "item_count",
        "license_label",
        "updated",
    )
    list_filter = ("published", "license_label")
    search_fields = ("collection_pk", "uuid", "collection__name")
    ordering = ("-updated",)
    readonly_fields = tuple(field.name for field in PublishedCollection._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ImageDecision)
class ImageDecisionAdmin(admin.ModelAdmin):
    """Editable, unlike PublishedCollection: this is the one piece of
    federation state a human is supposed to author."""

    list_display = ("image", "decision", "reason", "decided_by", "updated_at")
    list_filter = ("decision",)
    search_fields = ("image__id", "image__title", "reason")
    # raw_id, not autocomplete: autocomplete_fields would require the *host's*
    # ImageAdmin to declare search_fields, so installing this package could
    # fail another app's admin checks (admin.E040).
    raw_id_fields = ("image",)
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if obj.decided_by_id is None:
            obj.decided_by = request.user
        super().save_model(request, obj, form, change)
