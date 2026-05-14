"""Minimal Django settings used by the test suite."""

SECRET_KEY = 'aggrid-ssrm-test-secret-key-not-for-production'  # noqa: S105
DEBUG = False

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'aggrid_ssrm',
    'tests.test_app',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

USE_TZ = True
TIME_ZONE = 'UTC'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
