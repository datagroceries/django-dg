"""Markdown as every DataGroceries app shows it, and what the apps recognise in each other's text.

`render(text)` turns Markdown into safe HTML: lists read the way GitHub reads them, tables, fenced code,
"- [ ]" items as checkboxes, bare addresses as links, and nothing of whatever raw HTML the text holds
(nh3 strips it). `render_document(text)` does the same for a page of its own, such as a wiki page: with an
anchor on each heading, and the headings for a table of contents.

What an app recognises in text is a `Reference`, registered from its AppConfig.ready() with `register`:
the board makes "see T-123" a link to that ticket and "@anna" a mention of that colleague. Every app's
Markdown shows them so while that app is installed, and as plain text when it is not, so apps work
together without knowing each other.
"""

import html as html_module
import re
import typing
import xml.etree.ElementTree as ET

import markdown
import nh3
from django.utils.safestring import SafeString, mark_safe
from markdown.extensions import Extension, toc
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor

# Text in these is left as written: code, and what is a link already.
SKIPPED_TAGS = {'a', 'code', 'pre'}
# The headings a table of contents lists: not the title's level, nor the smallest.
HEADING_LEVELS = '2-4'


class Heading(typing.NamedTuple):
    level: int
    id: str
    name: str


class Reference(Treeprocessor):
    """Something an app recognises in text: each match of `pattern` that `resolve` finds becomes the
    element `element` makes. It runs on the rendered tree, so text inside code and existing links is
    left alone, and only what names something real is marked: "UTF-8" or "SHA-256" stay text.

    `name` and `priority` place it among Python-Markdown's tree processors; `classes` are the classes its
    elements may keep through sanitising, as {tag: {class, ...}}. `context` is what the caller of `render`
    said the text belongs to, such as {'wiki_page': page}, so a reference can be relative to it.
    """

    name: str
    priority: int = 5
    pattern: re.Pattern
    classes: dict[str, set[str]] = {}  # noqa: RUF012 - read only

    @property
    def context(self) -> dict:
        return self.md.dg_context

    @classmethod
    def help(cls) -> list[tuple[str, str]]:
        """What to write for it and what that gives, for the writing help beside the editor:
        [(example, explanation), ...]."""
        return []

    def resolve(self, matches: set[str]) -> dict:
        """What each match names, by match; matches that name nothing are left out."""
        raise NotImplementedError

    def element(self, match: str, found) -> ET.Element:
        raise NotImplementedError

    def run(self, root):
        matches = set()
        for element in root.iter():
            for text in (element.text, element.tail):
                matches.update(match[0] for match in self.pattern.finditer(text or ''))
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


REFERENCES: list[type[Reference]] = []


def register(reference: type[Reference]):
    """Have every app's Markdown mark up what `reference` recognises; from an AppConfig.ready()."""
    if reference not in REFERENCES:
        REFERENCES.append(reference)


class _References(Extension):
    def extendMarkdown(self, md):  # noqa: N802 - Markdown's name for it
        for reference in REFERENCES:
            md.treeprocessors.register(reference(md), reference.name, reference.priority)


# A list item, indented less than an indented code block would be at the top level.
LIST_ITEM_RE = re.compile(r'^( *)(?:[-*+]|\d+\.) +\S')
NESTED_INDENT = 4


class _ListPreprocessor(Preprocessor):
    """Reads lists the way GitHub and the editor's preview do, so a list shows as one once saved.

    Python-Markdown starts a list only after an empty line, and nests one only four spaces deep. Text
    written for GitHub does neither: "Steps:" followed by "- one" on the next line stays a paragraph with
    dashes, and an item indented by two spaces lands at the outer level. This puts the empty line in and
    deepens the indent, before Python-Markdown reads the text. Fenced code is set aside before this runs,
    so it is left alone.
    """

    def run(self, lines: list[str]) -> list[str]:
        result = []
        # The indents of the open list levels, outermost first; empty outside a list.
        levels = []
        for line in lines:
            item = LIST_ITEM_RE.match(line)
            if item and (levels or len(item[1]) < NESTED_INDENT):
                if not levels and result and result[-1].strip():
                    result.append('')
                indent = len(item[1])
                while levels and levels[-1] > indent:
                    levels.pop()
                if not levels or indent > levels[-1]:
                    levels.append(indent)
                result.append(' ' * NESTED_INDENT * (len(levels) - 1) + line.lstrip(' '))
                continue
            if line.strip() and not line.startswith((' ', '\t')) and not (result and result[-1].strip()):
                # Unindented text after an empty line ends the list.
                levels = []
            result.append(line)
        return result


class _GitHubLists(Extension):
    def extendMarkdown(self, md):  # noqa: N802 - Markdown's name for it
        # After fenced_code (25) has set code blocks aside.
        md.preprocessors.register(_ListPreprocessor(md), 'github_lists', 15)


def _anchor(value: str, separator: str) -> str:
    # Prefixed, so that no heading's id can take the name of something on the page around it.
    return f'h-{toc.slugify(value, separator)}'


def _convert(text: str, references: bool, headings: bool, context: dict | None) -> tuple[SafeString, list]:
    md = markdown.Markdown(
        extensions=[
            'fenced_code',
            'tables',
            'sane_lists',
            'nl2br',
            'pymdownx.magiclink',
            'pymdownx.tilde',
            'pymdownx.tasklist',
            _GitHubLists(),
            *([_References()] if references else []),
            *([toc.TocExtension(slugify=_anchor, toc_depth=HEADING_LEVELS)] if headings else []),
        ],
    )
    md.dg_context = context or {}
    html = md.convert(text)
    classes = {'li': {'task-list-item'}}
    for reference in REFERENCES if references else ():
        for tag, names in reference.classes.items():
            classes[tag] = classes.get(tag, set()) | names
    attributes = {**nh3.ALLOWED_ATTRIBUTES, 'input': {'checked'}}
    if headings:
        attributes |= {f'h{level}': {'id'} for level in range(1, 7)}
    cleaned = mark_safe(  # noqa: S308 - nh3 cleans it first
        nh3.clean(
            html,
            tags=nh3.ALLOWED_TAGS | {'input'},
            attributes=attributes,
            set_tag_attribute_values={'input': {'type': 'checkbox', 'disabled': ''}},
            allowed_classes=classes,
            attribute_filter=_anchors_only,
        ),
    )
    return cleaned, getattr(md, 'toc_tokens', [])


def _anchors_only(tag: str, attribute: str, value: str) -> str | None:
    """Ids are the headings' own, which _anchor made, not ones written in the text as raw HTML."""
    if attribute == 'id' and not value.startswith('h-'):
        return None
    return value


def render(text: str, *, references: bool = True, context: dict | None = None) -> SafeString:
    """`text` as HTML, with what the installed apps recognise marked up, unless `references` is False, as
    on a public page whose visitors could not open what they name. `context` is what the text belongs to,
    for the references (Reference.context). nh3 strips whatever raw HTML the
    Markdown let through and every class but the references' and the task item's, and makes every input
    that is left a disabled checkbox."""
    return _convert(text, references, headings=False, context=context)[0]


def render_document(
    text: str, *, references: bool = True, context: dict | None = None
) -> tuple[SafeString, list[Heading]]:
    """`text` as `render` makes it, with an id on each heading, and the headings of levels 2 to 4 for a
    table of contents, in order."""
    html, tokens = _convert(text, references, headings=True, context=context)
    found = []

    def walk(tokens):
        for token in tokens:
            found.append(Heading(token['level'], token['id'], html_module.unescape(token['name'])))
            walk(token['children'])

    walk(tokens)
    return html, found
