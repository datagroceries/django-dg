from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WikiConfig(AppConfig):
    name = 'gilde.wiki'
    label = 'gilde_wiki'
    verbose_name = _('Wiki')
    # Where gilde.urls mounts the wiki's pages.
    gilde_url_prefix = 'wiki'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from gilde.core import areas
        from gilde.wiki.mcp import AREA

        areas.register(AREA)
