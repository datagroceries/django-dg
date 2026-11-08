"""@-mentions, as every DataGroceries app reads them: "@anna" names the person whose handle is "anna"
(datagroceries.core.people) among the people of an area, the scope the text is written in.

`mentioned(scope, text)` says whom a text mentions, for the app to tell them; `Mentions` marks them in
Markdown (datagroceries.core.markdown), among the people of the scope the text belongs to (`context['scope']`), or
of any area when it does not say; `{% mention_people scope %}` lists them for the editor's suggestions.

Where not everyone may see what a text is on, such as a ticket in a group of its own, the app says so with
`visible_to`, a function of a person (`context['visible_to']` in Markdown): a mention of someone who cannot
see it is shown muted, in the text and while it is written, so the writer feels it does not reach them.
"""

import re
import typing
import xml.etree.ElementTree as ET

from django.utils.html import json_script
from django.utils.translation import gettext as _

from datagroceries.core import areas, markdown, people

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


def people_json(scope: str, visible_to=None) -> str:
    """The people a mention in `scope` reaches, as the editor's suggestions read them (editor.js); those
    for whom `visible_to` says no are marked unseen."""
    found = []
    for handle, user in people.by_handle(scope).items():
        person = {'handle': handle, 'name': people.name(user)}
        if visible_to is not None and not visible_to(user):
            person['unseen'] = True
        found.append(person)
    return json_script(found, 'dg-mention-people')


class Mentions(markdown.Reference):
    """ "@anna", shown as a mention of the colleague it names, with their name on hover; muted when they
    cannot see what the text is on (`context['visible_to']`)."""

    name = 'mentions'
    priority = 4
    pattern = MENTION_TEXT_RE
    classes: typing.ClassVar = {'span': {'dg-mention', 'dg-mention-unseen'}}

    @classmethod
    def help(cls):
        return [('@…', _('Type the start of a name to mention a colleague, who hears about it.'))]

    def resolve(self, matches):
        found = by_handle(self.context.get('scope'))
        # Each spelling as written, so "@Anna" and "@anna" are both found.
        return {match: found[match[1:].lower()] for match in matches if match[1:].lower() in found}

    def element(self, match, found):
        visible_to = self.context.get('visible_to')
        if visible_to is None or visible_to(found):
            mention = ET.Element('span', {'class': 'dg-mention', 'title': people.name(found)})
        else:
            title = _('%(person)s cannot see this') % {'person': people.name(found)}
            mention = ET.Element('span', {'class': 'dg-mention dg-mention-unseen', 'title': title})
        mention.text = match
        return mention
