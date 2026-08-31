#!/usr/bin/env python
"""Runs Django against the test settings.

This is a library, not a site, so this exists purely so contributors can do
``./manage.py test`` without exporting DJANGO_SETTINGS_MODULE by hand.
"""

import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
