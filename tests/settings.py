"""Settings for the adapter's own test suite.

Points Django at a PostGIS database and at the stubbed host app in
``tests/images``. Connection details come from the environment so the same
settings drive a local run and CI.
"""

import os

SECRET_KEY = "not-a-secret-this-is-the-test-suite"
DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.getenv("PGDATABASE", "panoramax_test"),
        "USER": os.getenv("PGUSER", "postgres"),
        "PASSWORD": os.getenv("PGPASSWORD", "postgres"),
        "HOST": os.getenv("PGHOST", "localhost"),
        "PORT": os.getenv("PGPORT", "5432"),
    }
}

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.gis",
    "tests.images",
    "yesterdays_panoramax",
]

ROOT_URLCONF = "tests.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Deliberately left at their defaults -- the suite turns federation on with
# override_settings, so the "unconfigured install publishes nothing" tests
# exercise the real defaults.
PANORAMAX_ENABLED = False
PANORAMAX_LICENSE_ALLOWLIST: dict[str, str] = {}
