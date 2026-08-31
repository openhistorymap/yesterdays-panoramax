"""Route names the adapter reverses when linking back to the host."""

from django.http import HttpResponse
from django.urls import path

app_name = "images"


def _stub(request, *args, **kwargs):
    return HttpResponse("")


urlpatterns = [
    path("image/<int:image_id>/", _stub, name="image_detail"),
    path("<slug:source_slug>/<slug:collection_slug>/", _stub, name="collection_detail"),
]
