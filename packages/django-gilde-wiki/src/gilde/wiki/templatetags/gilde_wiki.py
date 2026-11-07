from django import template
from django.conf import settings

from gilde.wiki.models import Page

register = template.Library()


@register.simple_tag
def wiki_name() -> str:
    return settings.GILDE_WIKI_NAME


def tree_context(current=None, also_open: Page | None = None) -> dict:
    """Every page, as the tree, opened down to `current`, the page shown, if any, and to where
    `also_open` is."""
    open_ids = set()
    if isinstance(current, Page) and current.pk:
        open_ids |= {above.pk for above in current.ancestors()} | {current.pk}
    if also_open is not None:
        open_ids |= {above.pk for above in also_open.ancestors()}
    return {'nodes': Page.objects.tree(), 'open_ids': open_ids, 'current': current}


@register.inclusion_tag('gilde_wiki/_tree.html')
def page_tree(current=None):
    return tree_context(current)
