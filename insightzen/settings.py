"""Django settings for the InsightZen project.

These settings configure the behaviour of the InsightZen application. It
defines installed apps, middleware, database configuration, static files
handling, template directories and more. Where appropriate, sensible
defaults have been chosen to make the project easy to run out of the box
with SQLite as the database backend.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a local .env file for development setups.
def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text().splitlines():
        if not line or line.strip().startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# Prefer a local .env file but fall back to .env.sample for convenience when the
# project is first checked out. The sample values are intentionally insecure and
# should be overridden in real deployments.
env_path = BASE_DIR / ".env"
sample_env_path = BASE_DIR / ".env.sample"

if env_path.exists():
    load_env_file(env_path)
elif sample_env_path.exists():
    warnings.warn(
        ".env not found; using values from .env.sample. Create a .env file to "
        "override these defaults.",
        RuntimeWarning,
        stacklevel=2,
    )
    load_env_file(sample_env_path)


def env_required(name: str) -> str:
    """Fetch a required environment variable or raise a helpful error."""

    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(
            f"Set the {name} environment variable (see .env.sample for defaults)."
        )
    return value


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env_required("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
# Default to disabled unless explicitly enabled via DJANGO_DEBUG.
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS: list[str] = ["185.204.171.78", "panel.insightzen.ir", "localhost", "127.0.0.1"]


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'insightzen.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Look for templates in the core application's templates directory
        'DIRS': [os.path.join(BASE_DIR, 'core', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'builtins': [
                'django.templatetags.static',
            ],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.language',
            ],
        },
    },
]

WSGI_APPLICATION = 'insightzen.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # Managed PostgreSQL instance that ships with the appliance.
        'NAME': os.getenv('PGDATABASE', 'insightzen3'),
        'USER': os.getenv('PGUSER', 'insightzen'),
        'PASSWORD': env_required('PGPASSWORD'),
        'HOST': env_required('PGHOST'),
        'PORT': env_required('PGPORT'),
        # Keep connections open for a minute to improve performance for repeated queries
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            # Prefer encrypted connections; can be overridden via PGSSLMODE
            'sslmode': os.getenv('PGSSLMODE', 'prefer'),
        },
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Singapore'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'core', 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Where Django should redirect after successful login
LOGIN_REDIRECT_URL = 'home'
LOGIN_URL = 'login'


# ---------------------------------------------------------------------------
# External data synchronisation settings
# ---------------------------------------------------------------------------

# Base URL for KoboToolbox / SurveyZen API requests.  The environment variable
# ``KOBO_BASE_URL`` takes precedence, falling back to the legacy ``HOST_BASE``
# flag used by the standalone ETL script so existing deployments continue to
# work without change.
KOBO_BASE_URL = os.getenv('KOBO_BASE_URL', os.getenv('HOST_BASE', 'https://panel.surveyzen.ir'))
KOBO_API_BASE = KOBO_BASE_URL.rstrip('/') + '/api/v2'

# Request timeout (seconds) and TLS configuration when contacting the Kobo
# API.  These mirror the ETL module defaults so that environments configured
# via environment variables retain the same behaviour.
KOBO_HTTP_TIMEOUT = int(os.getenv('KOBO_HTTP_TIMEOUT', os.getenv('HTTP_TIMEOUT_SEC', '60')))
KOBO_VERIFY_TLS = os.getenv('KOBO_VERIFY_TLS', os.getenv('VERIFY_TLS', 'True')).lower() not in ('false', '0', 'no')
KOBO_TLS_CERT = os.getenv('KOBO_TLS_CERT', os.getenv('CUSTOM_CA') or None)

# Location on disk where raw Kobo payloads for ``DatabaseEntry`` objects are
# cached.  Defaults to ``media/database_cache`` relative to the project base
# directory but can be overridden via ``DATABASE_CACHE_ROOT``.
DATABASE_CACHE_ROOT = Path(os.getenv('DATABASE_CACHE_ROOT', os.path.join(BASE_DIR, 'media', 'database_cache')))
