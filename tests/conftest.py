"""pytest-django configuration for the test suite."""
import django
from django.conf import settings


def pytest_configure(config):
    if not settings.configured:
        import os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
    django.setup()
