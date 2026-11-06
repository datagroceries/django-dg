"""Mark up ticket keys and @-mentions in rendered Markdown: "see T-123" links to that ticket, and
"@jaap" shows as a mention of that colleague.

Both run on the rendered tree, so text inside code and existing links is left alone, and each marks only
what names something real: "UTF-8" or "SHA-256" stay text, and so does an @-word that names no member.
"""

import re
import xml.etree.ElementTree as ET

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from gilde.board.conf import SCOPE
from gilde.board.models import KEY_RE, Ticket
from gilde.core import people

CANDIDATE_RE = re.compile(r'\b[A-Z][A-Z0-9]*-\d+\b')
# The handles notifications.MENTION_RE notifies, without a sentence's closing full stop.
MENTION_TEXT_RE = re.compile(r'(?<![\w@.])@[a-z0-9](?:[a-z0-9._-]*[a-z0-9_-])?', re.IGNORECASE)
SKIPPED_TAGS = {'a', 'code', 'pre'}


def resolve_keys(keys: set[str]) -> dict[str, Ticket]:
    """The tickets these keys name, by key; keys that name no ticket are left out."""
    ids = {int(match[1]) for key in keys if (match := KEY_RE.match(key))}
    found = {ticket.key: ticket for ticket in Ticket.objects.filter(pk__in=ids).only('pk', 'title')}
    return {key: ticket for key, ticket in found.items() if key in keys}


class _MarkupProcessor(Treeprocessor):
    """Replaces each match of `pattern` in the tree's text with an element, where `resolve` found what
    the match names."""

    pattern: re.Pattern

    def resolve(self, matches: set[str]) -> dict:
        """What each match names, by match; matches that name nothing are left out."""
        raise NotImplementedError

    def element(self, match: str, found) -> ET.Element:
        raise NotImplementedError

    def run(self, root):
        matches = set()
        for element in root.iter():
            matches.update(self.pattern.findall(element.text or ''))
            matches.update(self.pattern.findall(element.tail or ''))
        self.found = self.resolve(matches) if matches else {}
        # What this pass makes holds a match itself, so is not walked again.
        self.made = set()
        if self.found:
            self._walk(root)

    def _walk(self, element):
        if element.tag in SKIPPED_TAGS or element in self.made:
            return
        # The element's own text comes before its first child.
        for index, node in enumerate(self._split(element.text)):
            if index == 0:
                element.text = node
            else:
                element.insert(index - 1, node)
        position = 0
        while position < len(element):
            child = element[position]
            self._walk(child)
            # A child's tail is text of this element, after that child.
            pieces = self._split(child.tail)
            child.tail = pieces[0]
            for offset, node in enumerate(pieces[1:], start=1):
                element.insert(position + offset, node)
            position += len(pieces)

    def _split(self, text: str | None) -> list:
        """[text before the first match, its element, text after it as the element's tail, ...]; [text]
        without matches."""
        if not text:
            return [text]
        pieces = [None]
        last = 0
        for match in self.pattern.finditer(text):
            found = self.found.get(match[0])
            if found is None:
                continue
            before = text[last : match.start()]
            if len(pieces) == 1:
                pieces[0] = before
            else:
                pieces[-1].tail = before
            made = self.element(match[0], found)
            self.made.add(made)
            pieces.append(made)
            last = match.end()
        if len(pieces) == 1:
            return [text]
        pieces[-1].tail = text[last:]
        return pieces


class _TicketLinkProcessor(_MarkupProcessor):
    pattern = CANDIDATE_RE

    def resolve(self, matches):
        return resolve_keys(matches)

    def element(self, match, found):
        link = ET.Element('a', href=found.get_absolute_url(), title=found.title)
        link.text = match
        return link


class _MentionProcessor(_MarkupProcessor):
    """ "@jaap" names the person whose @-handle is "jaap" (gilde.core.people), as a notification does
    (notifications.mentioned_users)."""

    pattern = MENTION_TEXT_RE

    def resolve(self, matches):
        by_handle = people.by_handle(SCOPE)
        # Each spelling as written, so "@Anna" and "@anna" are both found.
        return {match: by_handle[match[1:].lower()] for match in matches if match[1:].lower() in by_handle}

    def element(self, match, found):
        mention = ET.Element('span', {'class': 'tk-mention', 'title': people.name(found)})
        mention.text = match
        return mention


class TicketLinkExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802 - Markdown's name for it
        md.treeprocessors.register(_TicketLinkProcessor(md), 'ticket_links', 5)
        md.treeprocessors.register(_MentionProcessor(md), 'ticket_mentions', 4)
