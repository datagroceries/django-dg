"""The board's references in Markdown (gilde.core.markdown): "see T-123" links to that ticket, and "@jaap"
shows as a mention of that colleague, in every Gilde app's Markdown while the board is installed.

Both mark only what names something real: "UTF-8" or "SHA-256" stay text, and so does an @-word that names
no member.
"""

import re
import typing
import xml.etree.ElementTree as ET

from gilde.board.conf import SCOPE
from gilde.board.models import KEY_RE, Ticket
from gilde.core import markdown, people

CANDIDATE_RE = re.compile(r'\b[A-Z][A-Z0-9]*-\d+\b')
# The handles notifications.MENTION_RE notifies, without a sentence's closing full stop.
MENTION_TEXT_RE = re.compile(r'(?<![\w@.])@[a-z0-9](?:[a-z0-9._-]*[a-z0-9_-])?', re.IGNORECASE)


def resolve_keys(keys: set[str]) -> dict[str, Ticket]:
    """The tickets these keys name, by key; keys that name no ticket are left out."""
    ids = {int(match[1]) for key in keys if (match := KEY_RE.match(key))}
    found = {ticket.key: ticket for ticket in Ticket.objects.filter(pk__in=ids).only('pk', 'title')}
    return {key: ticket for key, ticket in found.items() if key in keys}


class TicketLinks(markdown.Reference):
    name = 'ticket_links'
    priority = 5
    pattern = CANDIDATE_RE

    def resolve(self, matches):
        return resolve_keys(matches)

    def element(self, match, found):
        link = ET.Element('a', href=found.get_absolute_url(), title=found.title)
        link.text = match
        return link


class Mentions(markdown.Reference):
    """ "@jaap" names the person whose @-handle is "jaap" (gilde.core.people), as a notification does
    (notifications.mentioned_users)."""

    name = 'ticket_mentions'
    priority = 4
    pattern = MENTION_TEXT_RE
    classes: typing.ClassVar = {'span': {'tk-mention'}}

    def resolve(self, matches):
        by_handle = people.by_handle(SCOPE)
        # Each spelling as written, so "@Anna" and "@anna" are both found.
        return {match: by_handle[match[1:].lower()] for match in matches if match[1:].lower() in by_handle}

    def element(self, match, found):
        mention = ET.Element('span', {'class': 'tk-mention', 'title': people.name(found)})
        mention.text = match
        return mention
