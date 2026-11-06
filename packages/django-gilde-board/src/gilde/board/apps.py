from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BoardConfig(AppConfig):
    name = 'gilde.board'
    label = 'gilde_board'
    verbose_name = _('Board')
    # Where gilde.urls mounts the board's pages and API.
    gilde_url_prefix = 'board'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Here rather than at the top: the tools import the models, which are not ready before this.
        from gilde.board import checks  # noqa: F401 - registers the system checks
        from gilde.board.mcp import AREA
        from gilde.board.ticket_links import Mentions, TicketLinks
        from gilde.core import areas, markdown

        areas.register(AREA)
        markdown.register(TicketLinks)
        markdown.register(Mentions)
