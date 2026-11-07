"""The public demo on web1, demo.gildehq.com: anyone gets an account with one click and connects Claude to
it, and every night it starts again from the same board and wiki. How it runs is in README.md next to this
project.

To run it on a laptop, from this folder:

    mkdir -p /tmp/gilde-demo/data
    DJANGO_DEBUG=1 GILDE_DEMO_HOME=/tmp/gilde-demo DJANGO_SECRET_KEY=x python manage.py reset_demo
    DJANGO_DEBUG=1 GILDE_DEMO_HOME=/tmp/gilde-demo DJANGO_SECRET_KEY=x python manage.py runserver 8003
"""

import os
import pathlib

import sentry_sdk

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path(os.environ.get('GILDE_DEMO_HOME', '/srv/gilde-demo'))

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

# Errors go to Sentry (project gilde, organisation datagroceries, its US region) once SENTRY_DSN is in
# /srv/gilde-demo/.env. No personal data: no request bodies, which hold tickets and comments, and no IP
# addresses, cookies or user details (send_default_pii).
if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        environment='demo',
        send_default_pii=False,
        max_request_body_size='never',
    )
DEBUG = os.environ.get('DJANGO_DEBUG') == '1'
ALLOWED_HOSTS = ['localhost', '127.0.0.1'] if DEBUG else ['demo.gildehq.com']
CSRF_TRUSTED_ORIGINS = ['https://demo.gildehq.com']

# Caddy ends HTTPS, redirects plain HTTP to HTTPS itself, and passes on which it was.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 365 * 24 * 60 * 60
# Names of its own, so a laptop running the example project as well keeps both sign-ins.
SESSION_COOKIE_NAME = 'gilde_demo_session'
CSRF_COOKIE_NAME = 'gilde_demo_csrftoken'
# A visitor's account lasts until the night's reset anyway.
SESSION_COOKIE_AGE = 24 * 60 * 60
SILENCED_SYSTEM_CHECKS = [
    'security.W008',  # SECURE_SSL_REDIRECT: Caddy redirects
    # HSTS for this host only: gildehq.com's other hosts need not be served here.
    'security.W005',
    'security.W021',
    # http redirect URIs: Claude Code signs in through a loopback address (gilde.connect.conf).
    'oauth2_provider.W008',
]

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'rest_framework',
    'simple_history',
    'oauth2_provider',
    'gilde.core',
    'gilde.connect',
    'gilde.board',
    'gilde.wiki',
    'demo',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # The browser's language, or the one chosen in the top bar.
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'demo.urls'
WSGI_APPLICATION = 'demo.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
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

# SQLite, apart from Gilde's own instance: the demo is public, and the nightly reset empties it. Writes
# take the lock at once and wait their turn, rather than fail when two visitors save at the same moment.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # A folder of its own, as SQLite writes its journal files next to the database.
        'NAME': HOME / 'data' / 'db.sqlite3',
        'OPTIONS': {'transaction_mode': 'IMMEDIATE', 'timeout': 10, 'init_command': 'PRAGMA journal_mode=WAL;'},
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('nl', 'Nederlands')]
TIME_ZONE = 'UTC'
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = HOME / 'static'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
        if DEBUG
        else 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
    },
}
MEDIA_ROOT = HOME / 'media'

# The welcome page, with its button for an account: where the board and Claude's sign-in send a visitor
# who has none yet.
LOGIN_URL = 'welcome'

# Visitors have no email address, so there is nobody to mail.
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Errors to the journal (journalctl -u gilde-demo).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'django': {'handlers': ['console'], 'level': 'WARNING'}},
}

GILDE_BOARD_KEY_PREFIX = 'DEMO'
GILDE_BOARD_DISPLAY_TIMEZONE = 'Europe/Amsterdam'
