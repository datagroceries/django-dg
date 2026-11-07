"""System checks: what `manage.py check` tells whoever installs DataGroceries is still missing. Each message says
what to do."""

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core import checks
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

from datagroceries.core import areas, notifications

REQUIRED_APPS = ('rest_framework', 'simple_history')
CONTEXT_PROCESSORS = (
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
)


@checks.register
def check_apps(app_configs, **kwargs):
    return [
        checks.Error(
            f"DataGroceries needs '{app}' in INSTALLED_APPS.", hint=f"Add '{app}' to INSTALLED_APPS.", id='dg.E001'
        )
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
            f"The DataGroceries pages need the context processor '{processor}'.",
            hint="Add it to OPTIONS['context_processors'] of the DjangoTemplates engine in TEMPLATES.",
            id='dg.E002',
        )
        for processor in CONTEXT_PROCESSORS
        if processor not in processors
    ]


@checks.register
def check_urls(app_configs, **kwargs):
    try:
        reverse('dg_core:mcp')
    except NoReverseMatch:
        return [
            checks.Warning(
                "DataGroceries' pages and its MCP endpoint are not in the URLs.",
                hint="Add path('dg/', include('datagroceries.urls')) to the project's urlpatterns.",
                id='dg.W001',
            )
        ]
    try:
        resolve(resolve_url(settings.LOGIN_URL))
    except (Resolver404, NoReverseMatch):
        return [
            checks.Warning(
                f'LOGIN_URL ({settings.LOGIN_URL}) leads nowhere, so people who are not signed in cannot sign in '
                'to the DataGroceries pages.',
                hint="Set LOGIN_URL to the project's sign-in page, such as 'admin:login'.",
                id='dg.W002',
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
                    id='dg.W003',
                )
            )
    return found


@checks.register
def check_notifier(app_configs, **kwargs):
    try:
        notifications.notifier()
    except ImportError as error:
        return [
            checks.Error(
                f'DG_NOTIFIER cannot be imported: {error}',
                hint='Name a subclass of datagroceries.core.notifications.Notifier, or leave it out for email.',
                id='dg.E003',
            )
        ]
    return []
