"""Root URLconf for the test suite.

The adapter must be mounted at ``/api/``: the meta-catalogue's harvester builds
its requests as ``{instance_url}/api/collections`` with the prefix hardcoded.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("tests.images.urls", namespace="images")),
    path("api/", include("yesterdays_panoramax.urls", namespace="panoramax")),
]
