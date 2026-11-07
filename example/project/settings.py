"""A Django project to develop and try the DataGroceries apps in. Not for production."""

import os
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

SECRET_KEY = 'only-for-the-example-project'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'rest_framework',
    'simple_history',
    'oauth2_provider',
    'datagroceries.core',
    'datagroceries.connect',
    'datagroceries.board',
    'datagroceries.wiki',
    'project',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # The browser's language, of those below: to try the translations.
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
# PostgreSQL instead when POSTGRES_HOST is set, as in CI (.github/workflows/ci.yml); it needs psycopg.
if os.environ.get('POSTGRES_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'HOST': os.environ['POSTGRES_HOST'],
            'NAME': os.environ.get('POSTGRES_DB', 'datagroceries'),
            'USER': os.environ.get('POSTGRES_USER', 'datagroceries'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        }
    }
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('nl', 'Nederlands')]
TIME_ZONE = 'UTC'
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = 'admin:login'

# Notifications go to the console instead of anyone's inbox.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DG_BOARD_KEY_PREFIX = 'EX'
DG_BOARD_DISPLAY_TIMEZONE = 'Europe/Amsterdam'
