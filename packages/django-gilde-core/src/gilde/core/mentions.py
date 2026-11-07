"""@-mentions, as every Gilde app reads them: "@anna" names the person whose handle is "anna"
(gilde.core.people) among the people of an area, the scope the text is written in.

`mentioned(scope, text)` says whom a text mentions, for the app to tell them; `Mentions` marks them in
Markdown (gilde.core.markdown), among the people of the scope the text belongs to (`context['scope']`), or
of any area when it does not say; `{% mention_people scope %}` lists them for the editor's suggestions.
"""

import re
import typing
import xml.etree.ElementTree as ET

from django.utils.html import json_script
from django.utils.translation import gettext as _

from gilde.core import areas, markdown, people

# "@jasper" names the person whose handle is "jasper": not after a letter, "@" or "." (as in an email address).
MENTION_RE = re.compile(r'(?<![\w@.])@([a-z0-9][a-z0-9._-]*)', re.IGNORECASE)
# The same as text to mark, without a sentence's closing full stop.
MENTION_TEXT_RE = re.compile(r'(?<![\w@.])@[a-z0-9](?:[a-z0-9._-]*[a-z0-9_-])?', re.IGNORECASE)


def mentioned(scope: str, text: str) -> list:
    """The people of the area `scope` whom `text` @-mentions."""
    handles = {handle.lower().rstrip('.') for handle in MENTION_RE.findall(text or '')}
    return people.mentioned(scope, handles) if handles else []


def by_handle(scope: str | None) -> dict:
    """The people of the area `scope`, or of every area, by handle."""
    if scope is not None:
        return people.by_handle(scope)
    found = {}
    for each in areas.AREAS:
        found |= people.by_handle(each)
    return found


def people_json(scope: str) -> str:
    """The people a mention in `scope` reaches, as the editor's suggestions read them (editor.js)."""
    found = [{'handle': handle, 'name': people.name(user)} for handle, user in people.by_handle(scope).items()]
    return json_script(found, 'gilde-mention-people')


class Mentions(markdown.Reference):
    """ "@anna", shown as a mention of the colleague it names, with their name on hover."""

    name = 'mentions'
    priority = 4
    pattern = MENTION_TEXT_RE
    classes: typing.ClassVar = {'span': {'gilde-mention'}}

    @classmethod
    def help(cls):
        return [('@…', _('Type the start of a name to mention a colleague, who hears about it.'))]

    def resolve(self, matches):
        found = by_handle(self.context.get('scope'))
        # Each spelling as written, so "@Anna" and "@anna" are both found.
        return {match: found[match[1:].lower()] for match in matches if match[1:].lower() in found}

    def element(self, match, found):
        mention = ET.Element('span', {'class': 'gilde-mention', 'title': people.name(found)})
        mention.text = match
        return mention
