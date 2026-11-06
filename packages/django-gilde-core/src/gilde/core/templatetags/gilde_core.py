import functools
import pathlib

from django import template
from django.apps import apps
from django.conf import settings
from django.utils.translation import get_language_info

from gilde.core import people

register = template.Library()


@register.filter
def person_name(user) -> str:
    """A user's name as the Gilde apps show it (gilde.core.people), not their username, which may be an
    email address."""
    return people.name(user)


@functools.cache
def translated() -> frozenset[str]:
    """The languages the installed Gilde apps speak: English, in which they are written, and every
    language one of them has a translation for."""
    codes = {'en'}
    for config in apps.get_app_configs():
        if config.name.startswith('gilde.'):
            catalogs = pathlib.Path(config.path).glob('locale/*/LC_MESSAGES/django.mo')
            codes |= {catalog.parent.parent.name for catalog in catalogs}
    return frozenset(codes)


@register.simple_tag
def gilde_languages() -> list[tuple[str, str]]:
    """The languages to offer in the header, each with its own name for itself: those of the project's
    LANGUAGES that Gilde speaks too. None when there is no choice, or when the project does not follow
    a person's language (no LocaleMiddleware), as a choice would then change nothing."""
    if 'django.middleware.locale.LocaleMiddleware' not in settings.MIDDLEWARE:
        return []
    offered = [code for code, _name in settings.LANGUAGES if code.split('-')[0] in translated()]
    if len(offered) <= 1:
        return []
    return [(code, get_language_info(code)['name_local']) for code in offered]
