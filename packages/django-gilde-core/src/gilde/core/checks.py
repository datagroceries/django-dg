"""System checks: what `manage.py check` tells whoever installs Gilde is still missing. Each message says
what to do."""

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

from gilde.core import areas, notifications

REQUIRED_APPS = ('rest_framework', 'simple_history')
CONTEXT_PROCESSORS = (
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
)


@checks.register
def check_apps(app_configs, **kwargs):
    return [
        checks.Error(f"Gilde needs '{app}' in INSTALLED_APPS.", hint=f"Add '{app}' to INSTALLED_APPS.", id='gilde.E001')
        for app in REQUIRED_APPS
        if app not in settings.INSTALLED_APPS
    ]


@checks.register
def check_templates(app_configs, **kwargs):
    processors = {
        processor
        for engine in settings.TEMPLATES
        if engine['BACKEND'] == 'django.template.backends.django.DjangoTemplates'
        for processor in engine.get('OPTIONS', {}).get('context_processors', [])
    }
    return [
        checks.Error(
            f"The Gilde pages need the context processor '{processor}'.",
            hint="Add it to OPTIONS['context_processors'] of the DjangoTemplates engine in TEMPLATES.",
            id='gilde.E002',
        )
        for processor in CONTEXT_PROCESSORS
        if processor not in processors
    ]


@checks.register
def check_urls(app_configs, **kwargs):
    try:
        reverse('gilde_core:mcp')
    except NoReverseMatch:
        return [
            checks.Warning(
                "Gilde's pages and its MCP endpoint are not in the URLs.",
                hint="Add path('gilde/', include('gilde.urls')) to the project's urlpatterns.",
                id='gilde.W001',
            )
        ]
    try:
        resolve(resolve_url(settings.LOGIN_URL))
    except (Resolver404, NoReverseMatch):
        return [
            checks.Warning(
                f'LOGIN_URL ({settings.LOGIN_URL}) leads nowhere, so people who are not signed in cannot sign in '
                'to the Gilde pages.',
                hint="Set LOGIN_URL to the project's sign-in page, such as 'admin:login'.",
                id='gilde.W002',
            )
        ]
    return []


@checks.register
def check_people(app_configs, **kwargs):
    """An app that only superusers may use was most likely installed a moment ago."""
    found = []
    for area in areas.AREAS.values():
        app_label, codename = area.permission.split('.')
        try:
            granted = (
                Permission.objects.filter(content_type__app_label=app_label, codename=codename)
                .filter(Q(group__isnull=False) | Q(user__isnull=False))
                .exists()
            )
        except DatabaseError:  # not migrated yet
            return []
        if not granted:
            found.append(
                checks.Warning(
                    f'Only superusers may use {area.label} yet.',
                    hint=f'Grant the permission "{area.permission}" to a group in the admin, and put people in it.',
                    id='gilde.W003',
                )
            )
    return found


@checks.register
def check_notifications(app_configs, **kwargs):
    try:
        order = notifications.channels()
    except ImproperlyConfigured as error:
        return [checks.Error(str(error), hint="For example ['email'], or ['slack', 'email'].", id='gilde.E003')]
    if 'slack' in order and not getattr(settings, 'GILDE_SLACK_BOT_TOKEN', ''):
        return [
            checks.Error(
                'GILDE_NOTIFICATIONS includes Slack, but GILDE_SLACK_BOT_TOKEN is not set.',
                hint='Set it to the token of a Slack bot with the scopes users:read.email and chat:write.',
                id='gilde.E004',
            )
        ]
    return []
