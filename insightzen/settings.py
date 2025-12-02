"""Django settings for the InsightZen project.

These settings configure the behaviour of the InsightZen application. It
defines installed apps, middleware, database configuration, static files
handling, template directories and more. Where appropriate, sensible
defaults have been chosen to make the project easy to run out of the box
with SQLite as the database backend.
"""

from __future__ import annotations

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-CHANGE_ME_TO_A_RANDOM_SECRET_KEY'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS: list[str] = []


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
        # Database name defaults to 'insightzen' but can be overridden via environment variable
        'NAME': os.getenv('PGDATABASE', 'insightzen3'),
        # Database user defaults to 'postgres' but can be overridden via environment variable
        'USER': os.getenv('PGUSER', 'insightzen'),
        # Password for the database user; empty by default for local setups
        'PASSWORD': os.getenv('PGPASSWORD', 'K8RwWAPT5F7-?mrMBzR<'),
        # Host and port for PostgreSQL connection
        'HOST': os.getenv('PGHOST', '185.204.171.78'),
        'PORT': os.getenv('PGPORT', '5433'),
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


# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Where Django should redirect after successful login
LOGIN_REDIRECT_URL = 'home'
LOGIN_URL = 'login'
