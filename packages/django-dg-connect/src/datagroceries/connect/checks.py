"""What `manage.py check` says is missing for connecting agents, next to core's (datagroceries.core.checks)."""

from django.conf import settings
from django.core.checks import Error, register


@register
def check_apps(app_configs, **kwargs):
    if 'oauth2_provider' in settings.INSTALLED_APPS:
        return []
    return [
        Error(
            "Connecting agents needs django-oauth-toolkit, 'oauth2_provider', in INSTALLED_APPS.",
            hint="Add 'oauth2_provider' to INSTALLED_APPS.",
            id='dg_connect.E001',
        )
    ]
