import os

os.environ.setdefault('TULUN_MODE', 'development')

from .settings import *

TULUN_MODE = 'msd'
DEBUG = False
SECRET_KEY = 'isolated-tests-only-not-a-deployment-secret'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
if not os.environ.get('TULUN_TEST_DATABASE_URL'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
else:
    DATABASES = {'default': dj_database_url.parse(os.environ['TULUN_TEST_DATABASE_URL'])}
TULUN_ENABLE_LEGACY_UI = False
