"""Gilde's own instance on web1, gilde.datagroceries.com: Jasper's tickets, and the first installation of
Gilde outside the example project. How it runs is in README.md next to this project."""

import os
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path('/srv/gilde')

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = False
ALLOWED_HOSTS = ['gilde.datagroceries.com']
CSRF_TRUSTED_ORIGINS = ['https://gilde.datagroceries.com']

# Caddy ends HTTPS, redirects plain HTTP to HTTPS itself, and passes on which it was.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 365 * 24 * 60 * 60
SILENCED_SYSTEM_CHECKS = [
    'security.W008',  # SECURE_SSL_REDIRECT: Caddy redirects
    # HSTS for this host only: datagroceries.com's other hosts are not all served here.
    'security.W005',
    'security.W021',
    # http redirect URIs: Claude Code signs in through a loopback address (gilde.connect.conf).
    'oauth2_provider.W008',
]

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
    'gilde.core',
    'gilde.connect',
    'gilde.board',
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

ROOT_URLCONF = 'hq.urls'
WSGI_APPLICATION = 'hq.wsgi.application'

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

# PostgreSQL on the same server, through its socket, as the system user `gilde`: no password.
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'gilde', 'CONN_MAX_AGE': 60}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('nl', 'Nederlands')]
TIME_ZONE = 'UTC'
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = HOME / 'static'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
}
MEDIA_ROOT = HOME / 'media'

LOGIN_URL = 'admin:login'

# Mail through Hetzner's webhosting, from a mailbox of Gilde's own that only sends; datagroceries.com's SPF
# and DKIM allow it. The server, the mailbox and its password are in /srv/gilde/.env, not in this public
# repository. Until they are there, notifications go to the journal instead.
if os.environ.get('EMAIL_HOST_PASSWORD'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ['EMAIL_HOST']
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ['EMAIL_HOST_USER']
    EMAIL_HOST_PASSWORD = os.environ['EMAIL_HOST_PASSWORD']
    EMAIL_TIMEOUT = 10
    DEFAULT_FROM_EMAIL = SERVER_EMAIL = f'Gilde <{EMAIL_HOST_USER}>'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Errors to the journal (journalctl -u gilde), not to the admins by mail.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'django': {'handlers': ['console'], 'level': 'WARNING'}},
}

GILDE_BOARD_KEY_PREFIX = 'G'
GILDE_BOARD_DISPLAY_TIMEZONE = 'Europe/Amsterdam'
# Commits, branches and pull requests that name a ticket show on it. GitHub's webhook proves itself with
# the secret in /srv/gilde/.env; without one, the board accepts no delivery.
GILDE_BOARD_GITHUB_REPOSITORY = 'gildehq/gilde'
GILDE_BOARD_GITHUB_WEBHOOK_SECRET = os.environ.get('GILDE_BOARD_GITHUB_WEBHOOK_SECRET', '')
