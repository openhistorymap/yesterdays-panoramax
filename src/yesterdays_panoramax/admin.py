from django.contrib import admin

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
