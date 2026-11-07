from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WikiConfig(AppConfig):
    name = 'datagroceries.wiki'
    label = 'dg_wiki'
    verbose_name = _('Wiki')
    # Where datagroceries.urls mounts the wiki's pages.
    dg_url_prefix = 'wiki'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from datagroceries.core import areas, backlinks, markdown
        from datagroceries.wiki import search
        from datagroceries.wiki.conf import SCOPE
        from datagroceries.wiki.links import PageLinks
        from datagroceries.wiki.mcp import AREA

        areas.register(AREA)
        markdown.register(PageLinks)
        backlinks.register(backlinks.Source(SCOPE, _('Wiki pages'), search.naming))
