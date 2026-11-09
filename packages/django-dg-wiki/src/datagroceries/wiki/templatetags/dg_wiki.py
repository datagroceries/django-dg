from django import template
from django.conf import settings

from datagroceries.core import markdown, mentions
from datagroceries.wiki import access
from datagroceries.wiki.conf import SCOPE
from datagroceries.wiki.models import TOP, Page

register = template.Library()


def render_context(page: Page) -> dict:
    """What the wiki's Markdown belongs to: its page, for relative links and to mute the mentions of people
    who cannot see it, and the wiki, for mentions."""
    return {'wiki_page': page, 'scope': SCOPE, 'visible_to': access.visible_to(page)}


@register.filter
def wiki_markdown(text: str, page: Page) -> str:
    """Markdown written on `page`, as a comment on it."""
    return markdown.render(text, context=render_context(page))


@register.simple_tag
def wiki_name() -> str:
    return settings.DG_WIKI_NAME


@register.simple_tag
def wiki_mention_people(page: Page | None = None):
    """The people an @-mention in the wiki reaches, for the editor's suggestions, those who cannot see
    `page` marked; before dg_core/_editor_assets.html."""
    return mentions.people_json(SCOPE, access.visible_to(page) if page else None)


@register.simple_tag(takes_context=True)
def may_start_page(context) -> bool:
    """Whether the person may start a page anywhere: at the top, or under a page."""
    user = context['request'].user
    return access.may(user, access.WRITE, TOP) or bool(access.writable(user))


def tree_context(user, current=None, also_open: Page | None = None) -> dict:
    """The pages `user` may read, as the tree, opened down to `current`, the page shown, if any, and to
    where `also_open` is; the pages they may drag are `writable`."""
    open_ids = set()
    if isinstance(current, Page) and current.pk:
        open_ids |= {above.pk for above in current.ancestors()} | {current.pk}
    if also_open is not None:
        open_ids |= {above.pk for above in also_open.ancestors()}
    nodes = access.tree(user)
    return {'nodes': nodes, 'open_ids': open_ids, 'current': current, 'writable': access.writable(user)}


@register.inclusion_tag('dg_wiki/_tree.html', takes_context=True)
def page_tree(context, current=None):
    return tree_context(context['request'].user, current)
