"""The board's reference in Markdown (datagroceries.core.markdown): "see T-123" links to that ticket, in every
DataGroceries app's Markdown while the board is installed. It marks only what names a ticket: "UTF-8" or "SHA-256"
stay text.
"""

import re
import xml.etree.ElementTree as ET

from django.conf import settings
from django.utils.translation import gettext as _

from datagroceries.board.models import KEY_RE, Ticket
from datagroceries.core import markdown

CANDIDATE_RE = re.compile(r'\b[A-Z][A-Z0-9]*-\d+\b')


def resolve_keys(keys: set[str]) -> dict[str, Ticket]:
    """The tickets these keys name, by key; keys that name no ticket are left out."""
    ids = {int(match[1]) for key in keys if (match := KEY_RE.match(key))}
    found = {ticket.key: ticket for ticket in Ticket.objects.filter(pk__in=ids).only('pk', 'title')}
    return {key: ticket for key, ticket in found.items() if key in keys}


class TicketLinks(markdown.Reference):
    name = 'ticket_links'
    priority = 5
    pattern = CANDIDATE_RE

    @classmethod
    def help(cls):
        return [(f'{settings.DG_BOARD_KEY_PREFIX}-123', _('A link to that ticket.'))]

    def resolve(self, matches):
        return resolve_keys(matches)

    def element(self, match, found):
        link = ET.Element('a', href=found.get_absolute_url(), title=found.title)
        link.text = match
        return link
