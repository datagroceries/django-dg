"""Markdown as every DataGroceries app shows it, and what the apps recognise in each other's text.

The Markdown is GitHub Flavored Markdown (GFM, on CommonMark), as GitHub shows it in an issue or a comment,
read by markdown-it-py: tables, task lists, strikethrough, bare addresses as links, alerts ("> [!NOTE]")
and footnotes, and a new line is a line break. `render(text)` turns it into safe HTML: nh3 keeps the raw
HTML it knows to be harmless, such as <details> or <kbd>, and drops the rest. `render_document(text)` does
the same for a page of its own, such as a wiki page: with an anchor on each heading, and the headings for a
table of contents.

What an app recognises in text is a `Reference`, registered from its AppConfig.ready() with `register`:
the board makes "see T-123" a link to that ticket and "@anna" a mention of that colleague. Every app's
Markdown shows them so while that app is installed, and as plain text when it is not, so apps work
together without knowing each other.
"""

import functools
import hashlib
import re
import typing
import unicodedata
import xml.etree.ElementTree as ET

import nh3
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.gfm import gfm_plugin

# The headings a table of contents lists: not the title's level, nor the smallest.
HEADING_LEVELS = range(2, 5)
# GitHub's alerts, each with its icon and title: a quote whose first line is "[!NOTE]" and so on.
ALERTS = {
    'note': ('info-circle', _('Note')),
    'tip': ('lightbulb', _('Tip')),
    'important': ('chat-square-text', _('Important')),
    'warning': ('exclamation-triangle', _('Warning')),
    'caution': ('exclamation-octagon', _('Caution')),
}
# The classes the rendered Markdown keeps through sanitising, by tag, as GitHub names them.
CLASSES = {
    'ul': {'contains-task-list'},
    'li': {'task-list-item', 'footnote-item'},
    'div': {'markdown-alert', *(f'markdown-alert-{kind}' for kind in ALERTS)},
    'p': {'markdown-alert-title'},
    'i': {'bi', *(f'bi-{icon}' for icon, _title in ALERTS.values())},
    'sup': {'footnote-ref'},
    'a': {'footnote-backref'},
    'hr': {'footnotes-sep'},
    'section': {'footnotes'},
    'ol': {'footnotes-list'},
}
# The ids the rendered Markdown keeps: its headings' (_anchor), and its footnotes', which carry the text's
# own `docId` so that two texts on one page do not share them.
ID_RE = re.compile(r'h-[\w-]*|fn(ref)?-[0-9a-f]{8}-\d+(:\d+)?')


class Heading(typing.NamedTuple):
    level: int
    id: str
    name: str


class Reference:
    """Something an app recognises in text: each match of `pattern` that `resolve` finds becomes the
    element `element` makes. It looks only at the text itself, so text inside code, links and images is
    left alone, and only what names something real is marked: "UTF-8" or "SHA-256" stay text.

    `name` names it; references with a higher `priority` go first. `classes` are the classes its elements
    may keep through sanitising, as {tag: {class, ...}}. `context` is what the caller of `render` said the
    text belongs to, such as {'wiki_page': page}, so a reference can be relative to it. `help_heading`, if
    any, gives its rows in the writing help a part of their own under that heading; without one they
    follow Markdown's.
    """

    name: str
    priority: int = 5
    pattern: re.Pattern
    classes: dict[str, set[str]] = {}  # noqa: RUF012 - read only
    help_heading: str = ''

    def __init__(self, context: dict):
        self._context = context

    @property
    def context(self) -> dict:
        return self._context

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

    def apply(self, tokens: list[Token]):
        """Marks up what it finds in the text of `tokens`, the parsed Markdown, asking `resolve` once."""
        inlines = [token for token in tokens if token.type == 'inline' and token.children]
        matches = {
            match[0]
            for inline in inlines
            for child in _texts(inline.children)
            for match in self.pattern.finditer(child.content)
        }
        found = self.resolve(matches) if matches else {}
        if not found:
            return
        for inline in inlines:
            texts = set(map(id, _texts(inline.children)))
            inline.children = [
                piece
                for child in inline.children
                for piece in (self._split(child.content, found) if id(child) in texts else [child])
            ]

    def _split(self, text: str, found: dict) -> list[Token]:
        """The text as tokens: the text before each match that names something, then its element."""
        pieces, last = [], 0
        for match in self.pattern.finditer(text):
            if match[0] not in found:
                continue
            pieces.append(_token('text', text[last : match.start()]))
            made = self.element(match[0], found[match[0]])
            for each in made.iter():
                # In order, as the text's own HTML has them.
                each.attrib = dict(sorted(each.attrib.items()))
            pieces.append(_token('html_inline', ET.tostring(made, encoding='unicode', method='html')))
            last = match.end()
        pieces.append(_token('text', text[last:]))
        return [piece for piece in pieces if piece.content]


def _token(kind: str, content: str) -> Token:
    return Token(kind, '', 0, content=content)


def _texts(children: list[Token]):
    """The text tokens of a line of Markdown that are not a link's own."""
    depth = 0
    for child in children:
        depth += {'link_open': 1, 'link_close': -1}.get(child.type, 0)
        if child.type == 'text' and not depth:
            yield child


REFERENCES: list[type[Reference]] = []


def register(reference: type[Reference]):
    """Have every app's Markdown mark up what `reference` recognises; from an AppConfig.ready()."""
    if reference not in REFERENCES:
        REFERENCES.append(reference)


@functools.cache
def _parser(*, breaks: bool = True) -> MarkdownIt:
    """GFM, as in a comment on GitHub, where a new line is a line break (`breaks`); raw HTML is read, for nh3
    to sort."""
    return MarkdownIt('commonmark', {'html': True, 'breaks': breaks}).use(gfm_plugin)


def _as_github(tokens: list[Token]):
    """The HTML the GFM spec gives where markdown-it-py writes another: <del> for struck text, and a table's
    alignment as `align`, which nh3 keeps, where a style would be dropped."""
    for token in tokens:
        if token.type in ('s_open', 's_close'):
            token.tag = 'del'
        elif token.type in ('th_open', 'td_open') and (style := token.attrGet('style')):
            token.attrs = {'align': str(style).removeprefix('text-align:')}
        if token.children:
            _as_github(token.children)


def _alerts(tokens: list[Token]):
    """An alert's title in the language of the page, after its icon. An alert inside a list or another quote
    is a quote, as GitHub has alerts only at the top, its first line as written."""
    nested = []
    for index, token in enumerate(tokens):
        if token.type == 'alert_open' and token.level:
            token.type, token.tag, token.attrs = 'blockquote_open', 'blockquote', {}
            nested.append(token.level)
            tokens[index + 1].type, tokens[index + 1].attrs = 'paragraph_open', {}
            tokens[index + 2].children = [_token('text', f'[!{token.info}]')]
            tokens[index + 3].type = 'paragraph_close'
        elif token.type == 'alert_close' and nested and token.level == nested[-1]:
            token.type, token.tag = 'blockquote_close', 'blockquote'
            nested.pop()
        elif token.type == 'alert_title_open' and tokens[index - 1].type == 'alert_open':
            icon, title = ALERTS[tokens[index - 1].meta['kind'].lower()]
            icon_html = f'<i class="bi bi-{icon}"></i> '
            tokens[index + 1].children = [_token('html_inline', icon_html), _token('text', str(title))]


def _slug(value: str) -> str:
    """A heading's text as an address, as Python-Markdown's table of contents made it."""
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', value).strip().lower())


def _anchors(tokens: list[Token]) -> list[Heading]:
    """An id on each heading, prefixed, so that none can take the name of something on the page around it;
    the headings for a table of contents."""
    found, taken = [], set()
    for index, token in enumerate(tokens):
        if token.type != 'heading_open':
            continue
        name = ''.join(child.content for child in tokens[index + 1].children if child.type in ('text', 'code_inline'))
        anchor = base = f'h-{_slug(name)}'
        number = 0
        while anchor in taken:
            number += 1
            anchor = f'{base}_{number}'
        taken.add(anchor)
        token.attrSet('id', anchor)
        if int(token.tag[1]) in HEADING_LEVELS:
            found.append(Heading(int(token.tag[1]), anchor, name))
    return found


def _convert(text: str, references: bool, headings: bool, context: dict | None) -> tuple[SafeString, list]:
    parser = _parser()
    env = {'docId': hashlib.sha256((text or '').encode()).hexdigest()[:8]}
    tokens = parser.parse(text or '', env)
    _as_github(tokens)
    _alerts(tokens)
    found = _anchors(tokens) if headings else []
    for reference in sorted(REFERENCES, key=lambda each: -each.priority) if references else ():
        reference(context or {}).apply(tokens)
    html = parser.renderer.render(tokens, parser.options, env).strip()
    classes = {tag: set(names) for tag, names in CLASSES.items()}
    for reference in REFERENCES if references else ():
        for tag, names in reference.classes.items():
            classes[tag] = classes.get(tag, set()) | names
    # Footnotes link to each other by id.
    attributes = {**nh3.ALLOWED_ATTRIBUTES, 'input': {'checked'}, 'a': {*nh3.ALLOWED_ATTRIBUTES['a'], 'id'}}
    attributes['li'] = {'id'}
    if headings:
        attributes |= {f'h{level}': {'id'} for level in range(1, 7)}
    cleaned = mark_safe(  # noqa: S308 - nh3 cleans it first
        nh3.clean(
            html,
            tags=nh3.ALLOWED_TAGS | {'input', 'section'},
            attributes=attributes,
            set_tag_attribute_values={'input': {'type': 'checkbox', 'disabled': ''}},
            allowed_classes=classes,
            attribute_filter=_own_ids,
        ),
    )
    return cleaned, found


def _own_ids(tag: str, attribute: str, value: str) -> str | None:
    """Ids are the headings' and footnotes' own, not ones written in the text as raw HTML."""
    if attribute == 'id' and not ID_RE.fullmatch(value):
        return None
    return value


def render(text: str, *, references: bool = True, context: dict | None = None) -> SafeString:
    """`text` as HTML, with what the installed apps recognise marked up, unless `references` is False, as
    on a public page whose visitors could not open what they name. `context` is what the text belongs to,
    for the references (Reference.context). nh3 strips whatever raw HTML is not harmless, and every class
    but GitHub's own and the references', and makes every input that is left a disabled checkbox."""
    return _convert(text, references, headings=False, context=context)[0]


def render_document(
    text: str, *, references: bool = True, context: dict | None = None
) -> tuple[SafeString, list[Heading]]:
    """`text` as `render` makes it, with an id on each heading, and the headings of levels 2 to 4 for a
    table of contents, in order."""
    return _convert(text, references, headings=True, context=context)
