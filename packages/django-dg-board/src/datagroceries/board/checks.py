"""The board's system checks, next to core's (datagroceries.core.checks)."""

from django.conf import settings
from django.core.checks import Error, register


@register
def check_apps(app_configs, **kwargs):
    if 'django.contrib.humanize' in settings.INSTALLED_APPS:
        return []
    return [
        Error(
            "The board needs 'django.contrib.humanize' in INSTALLED_APPS.",
            hint="Add 'django.contrib.humanize' to INSTALLED_APPS.",
            id='dg_board.E001',
        )
    ]
