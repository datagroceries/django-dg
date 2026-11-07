from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BoardConfig(AppConfig):
    name = 'datagroceries.board'
    label = 'dg_board'
    verbose_name = _('Board')
    # Where datagroceries.urls mounts the board's pages and API.
    dg_url_prefix = 'board'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Here rather than at the top: the tools import the models, which are not ready before this.
        from datagroceries.board import checks  # noqa: F401 - registers the system checks
        from datagroceries.board.mcp import AREA
        from datagroceries.board.ticket_links import TicketLinks
        from datagroceries.core import areas, markdown

        areas.register(AREA)
        markdown.register(TicketLinks)
