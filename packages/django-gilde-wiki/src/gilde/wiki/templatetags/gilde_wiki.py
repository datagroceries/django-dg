from django import template
from django.conf import settings

from gilde.wiki.models import Page

register = template.Library()


@register.simple_tag
def wiki_name() -> str:
    return settings.GILDE_WIKI_NAME


@register.inclusion_tag('gilde_wiki/_tree.html')
def page_tree(current=None):
    """Every page, as the tree, opened down to `current`, the page shown, if any."""
    if isinstance(current, Page) and current.pk:
        open_ids = {page.pk for page in current.ancestors()} | {current.pk}
    else:
        open_ids = set()
    return {'nodes': Page.objects.tree(), 'open_ids': open_ids, 'current': current}
