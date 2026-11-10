"""DataGroceries' own instance on web1, hq.datagroceries.com: Jasper's tickets and wiki, with a public part
of the wiki. How it runs is in README.md next to this project."""

import os
import pathlib

import sentry_sdk

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path('/srv/gilde')

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

# Errors go to Sentry (project gilde, organisation datagroceries, its US region) once SENTRY_DSN is in
# /srv/gilde/.env. No personal data: no request bodies, which hold tickets and comments, and no IP
# addresses, cookies or user details (send_default_pii).
if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        environment='production',
        send_default_pii=False,
        max_request_body_size='never',
    )
DEBUG = False
ALLOWED_HOSTS = ['hq.datagroceries.com']
CSRF_TRUSTED_ORIGINS = ['https://hq.datagroceries.com']

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
    # http redirect URIs: Claude Code signs in through a loopback address (datagroceries.connect.conf).
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
    'datagroceries.core',
    'datagroceries.connect',
    'datagroceries.board',
    'datagroceries.wiki',
    'allauth',
    'allauth.account',
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
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'hq.urls'
WSGI_APPLICATION = 'hq.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # hq's own: allauth's pages in DataGroceries' layout.
        'DIRS': [BASE_DIR / 'hq' / 'templates'],
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
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'datagroceries', 'CONN_MAX_AGE': 60}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('nl', 'Nederlands')]
TIME_ZONE = 'Europe/Amsterdam'
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = HOME / 'static'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
}
MEDIA_ROOT = HOME / 'media'

# Anyone reads the wiki's public folders; to comment there, they make an account with their email address
# and a name, and sign in with a code mailed to them, without a password (hq/people.py). So does Jasper,
# or with his password in the admin.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = '/'
ACCOUNT_ADAPTER = 'hq.accounts.AccountAdapter'
ACCOUNT_SIGNUP_FORM_CLASS = 'hq.accounts.SignupForm'
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*']
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
# Signed in for as long as the session lasts, without a box to tick.
ACCOUNT_SESSION_REMEMBER = True
# An account works once its address is confirmed, with a code mailed to it.
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[DataGroceries] '
# Against bots: a field people do not see, which bots fill in, and few sign-ups per address.
ACCOUNT_SIGNUP_FORM_HONEYPOT_FIELD = 'website'
ACCOUNT_RATE_LIMITS = {'signup': '5/h/ip', 'login': '20/m/ip', 'request_login_code': '10/h/ip,3/h/key'}
# The rate limits count in a cache that every gunicorn worker shares.
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache', 'LOCATION': HOME / 'cache'}}

# Mail through Hetzner's webhosting, from a mailbox of DataGroceries' own that only sends; datagroceries.com's SPF
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
    DEFAULT_FROM_EMAIL = SERVER_EMAIL = f'DataGroceries <{EMAIL_HOST_USER}>'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Errors to the journal (journalctl -u gilde), not to the admins by mail.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'django': {'handlers': ['console'], 'level': 'WARNING'}},
}

DG_PEOPLE = 'hq.people.HqPeople'
DG_BOARD_KEY_PREFIX = 'G'
# Commits, branches and pull requests that name a ticket show on it. GitHub's webhook proves itself with
# the secret in /srv/gilde/.env; without one, the board accepts no delivery.
DG_BOARD_GITHUB_REPOSITORY = 'datagroceries/django-dg'
DG_BOARD_GITHUB_WEBHOOK_SECRET = os.environ.get('DG_BOARD_GITHUB_WEBHOOK_SECRET', '')
