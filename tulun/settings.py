import os
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
TULUN_MODE = os.environ.get('TULUN_MODE', 'msd')
if TULUN_MODE not in ('msd', 'development'):
    raise ImproperlyConfigured('TULUN_MODE must be msd or development.')
if TULUN_MODE == 'development':
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env', override=False)


def bounded_integer(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        raise ImproperlyConfigured(f'{name} must be an integer.') from None
    if not minimum <= value <= maximum:
        raise ImproperlyConfigured(f'{name} is outside its supported range.')
    return value


DEBUG = TULUN_MODE == 'development' and os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if TULUN_MODE == 'msd' and (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5):
    raise ImproperlyConfigured('A strong DJANGO_SECRET_KEY of at least 50 characters is required.')
if not SECRET_KEY:
    SECRET_KEY = 'development-only-not-for-msd-use'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost 127.0.0.1').replace(',', ' ').split()
if TULUN_MODE == 'msd' and (not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must contain explicit hosts.')

TULUN_API_KEY = os.environ.get('TULUN_API_KEY', '')
AI_GATEWAY_BASE_URL = os.environ.get('AI_GATEWAY_BASE_URL', '').rstrip('/')
AI_GATEWAY_API_KEY = os.environ.get('AI_GATEWAY_API_KEY', '')
AI_GATEWAY_MODELS = tuple(os.environ.get('AI_GATEWAY_MODELS', '').replace(',', ' ').split())
if AI_GATEWAY_BASE_URL:
    gateway_url = urlsplit(AI_GATEWAY_BASE_URL)
    allow_http = os.environ.get('AI_GATEWAY_ALLOW_INSECURE_HTTP', 'false').lower() == 'true'
    if (gateway_url.scheme not in (('https', 'http') if allow_http else ('https',))
            or not gateway_url.hostname or gateway_url.username or gateway_url.password
            or gateway_url.query or gateway_url.fragment or not gateway_url.path.endswith('/v1')):
        raise ImproperlyConfigured('AI_GATEWAY_BASE_URL must be an approved URL ending in /v1.')
if TULUN_API_KEY and TULUN_API_KEY == AI_GATEWAY_API_KEY:
    raise ImproperlyConfigured('Client and Gateway credentials must be different.')

TULUN_MAX_TEXT_LENGTH = bounded_integer('TULUN_MAX_TEXT_LENGTH', 4000, 1, 16000)
TULUN_MAX_BODY_BYTES = bounded_integer('TULUN_MAX_BODY_BYTES', 32768, 1024, 131072)
AI_GATEWAY_TIMEOUT_SECONDS = bounded_integer('AI_GATEWAY_TIMEOUT_SECONDS', 15, 1, 30)
AI_GATEWAY_MAX_OUTPUT_TOKENS = bounded_integer('AI_GATEWAY_MAX_OUTPUT_TOKENS', 2048, 16, 4096)
TULUN_TRANSLATION_TIMEOUT_SECONDS = bounded_integer('TULUN_TRANSLATION_TIMEOUT_SECONDS', 60, 5, 90)
TULUN_MAX_PROMPT_CHARS = bounded_integer('TULUN_MAX_PROMPT_CHARS', 24000, 1000, 64000)
TULUN_MAX_RETRIEVED_SENTENCES = bounded_integer('TULUN_MAX_RETRIEVED_SENTENCES', 5, 0, 10)
DATA_UPLOAD_MAX_MEMORY_SIZE = TULUN_MAX_BODY_BYTES
APPEND_SLASH = False

database_url = os.environ.get('DATABASE_URL', '')
if database_url:
    if urlsplit(database_url).scheme not in ('postgres', 'postgresql'):
        raise ImproperlyConfigured('DATABASE_URL must use PostgreSQL.')
    try:
        DATABASES = {'default': dj_database_url.parse(
            database_url, conn_max_age=60, conn_health_checks=True,
        )}
    except (ValueError, KeyError):
        raise ImproperlyConfigured('DATABASE_URL is invalid.') from None
    database_options = DATABASES['default'].setdefault('OPTIONS', {})
    database_options.setdefault('connect_timeout', 5)
    database_options.setdefault('options', '-c statement_timeout=10000')
elif TULUN_MODE == 'development':
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('TULUN_SQLITE_PATH', str(BASE_DIR / 'db.sqlite3')),
        'OPTIONS': {'timeout': 5},
    }}
else:
    raise ImproperlyConfigured('DATABASE_URL is required in MSD mode.')

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'translations',
]
MIDDLEWARE = [
    'tulun.middleware.ApiBoundaryMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'tulun.urls'
WSGI_APPLICATION = 'tulun.wsgi.application'
ASGI_APPLICATION = 'tulun.asgi.application'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
AUTH_USER_MODEL = 'translations.CustomUser'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = TULUN_MODE == 'msd'
CSRF_COOKIE_SECURE = TULUN_MODE == 'msd'
SECURE_CONTENT_TYPE_NOSNIFF = True
CSRF_TRUSTED_ORIGINS = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split()
TULUN_ENABLE_LEGACY_UI = TULUN_MODE == 'development' and os.environ.get('TULUN_ENABLE_LEGACY_UI', 'false').lower() == 'true'
LOGIN_REDIRECT_URL = '/'
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'tulun.api': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django.request': {'handlers': ['logging_null'], 'propagate': False},
        'django.security': {'handlers': ['logging_null'], 'propagate': False},
        'LiteLLM': {'handlers': ['logging_null'], 'propagate': False},
        'LiteLLM Proxy': {'handlers': ['logging_null'], 'propagate': False},
        'LiteLLM Router': {'handlers': ['logging_null'], 'propagate': False},
        'httpx': {'handlers': ['logging_null'], 'propagate': False},
    },
}
LOGGING['handlers']['logging_null'] = {'class': 'logging.NullHandler'}
