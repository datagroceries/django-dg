import functools
import pathlib

from django import template
from django.apps import apps
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse
from django.utils.translation import get_language_info

from datagroceries.core import areas, markdown, mentions, people

register = template.Library()


@register.filter
def person_name(user) -> str:
    """A user's name as the DataGroceries apps show it (datagroceries.core.people), not their username, which may be an
    email address."""
    return people.name(user)


@register.filter
def render_markdown(text: str, context: dict | None = None) -> str:
    """Markdown as every DataGroceries app shows it (datagroceries.core.markdown), with what the text
    belongs to as `context` (Reference.context), such as {'visible_to': ...} for its mentions."""
    return markdown.render(text, context=context or None)


@register.simple_tag
def mention_people(scope: str):
    """The people an @-mention in the area `scope` reaches, for the editor's suggestions; before
    dg_core/_editor_assets.html."""
    return mentions.people_json(scope)


@register.simple_tag(takes_context=True)
def dg_apps(context) -> list[dict]:
    """The DataGroceries apps the person may use, to switch between at the top of the page, the one shown marked;
    none with only one, as there is nothing to switch to."""
    request = context.get('request')
    if request is None or not request.user.is_authenticated:
        return []
    found = [
        {'label': area.label, 'icon': area.icon, 'url': reverse(area.home)}
        for scope, area in areas.AREAS.items()
        if area.home and people.may_use(request.user, scope)
    ]
    for app in found:
        app['current'] = request.path.startswith(app['url'])
    return found if len(found) > 1 else []


@register.simple_tag(takes_context=True)
def sign_in_url(context) -> str:
    """The project's sign-in page (LOGIN_URL), coming back to the page shown, for someone who reads it
    without being signed in."""
    return redirect_to_login(context['request'].get_full_path()).url


@register.inclusion_tag('dg_core/_markdown_help.html')
def markdown_help() -> dict:
    """How to write Markdown, and what the installed apps recognise in it, for beside the editor: the rows
    of references without a heading after Markdown's, then a part per heading."""
    parts = {}
    for reference in markdown.REFERENCES:
        parts.setdefault(str(reference.help_heading), []).extend(reference.help())
    return {'references': parts.pop('', []), 'parts': [part for part in parts.items() if part[1]]}


@functools.cache
def translated() -> frozenset[str]:
    """The languages the installed DataGroceries apps speak: English, in which they are written, and every
    language one of them has a translation for."""
    codes = {'en'}
    for config in apps.get_app_configs():
        if config.name.startswith('datagroceries.'):
            catalogs = pathlib.Path(config.path).glob('locale/*/LC_MESSAGES/django.mo')
            codes |= {catalog.parent.parent.name for catalog in catalogs}
    return frozenset(codes)


@register.simple_tag
def dg_languages() -> list[tuple[str, str]]:
    """The languages to offer in the header, each with its own name for itself: those of the project's
    LANGUAGES that DataGroceries speaks too. None when there is no choice, or when the project does not follow
    a person's language (no LocaleMiddleware), as a choice would then change nothing."""
    if 'django.middleware.locale.LocaleMiddleware' not in settings.MIDDLEWARE:
        return []
    offered = [code for code, _name in settings.LANGUAGES if code.split('-')[0] in translated()]
    if len(offered) <= 1:
        return []
    return [(code, get_language_info(code)['name_local']) for code in offered]
