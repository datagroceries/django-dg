"""Links to wiki pages: "[[Engineering/Deploying]]" links to that page, and "[[Deploying|how we ship]]"
does with words of its own, in every Gilde app's Markdown while the wiki is installed (gilde.core.markdown),
so a ticket can link to a page too.

A link names a page by its address, written in titles or in slugs: "Engineering/Deploying" and
"engineering/deploying" are the same. The end of an address will do: "[[Deploying]]" finds
"engineering/deploying", the page highest in the tree if several addresses end so. An address a page had
before a rename or a move still finds it. A link to no page shows as one, and leads to where that page
can be started.

The wiki keeps the links in its own pages (Link): to list what links to a page, and to rewrite them when
a page they name gets another address, so they keep saying where the page is.
"""

import dataclasses
import re
import typing
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _

from gilde.core import markdown
from gilde.wiki.models import PATH_LENGTH, FormerPath, Link, Page, slug_of

LINK_RE = re.compile(r'\[\[([^\[\]|\n]+)(?:\|([^\[\]\n]+))?\]\]')
# Fenced and inline code, where "[[...]]" is text as written, as Markdown shows it.
CODE_RE = re.compile(r'^(```|~~~).*?^\1|`[^`\n]+`', re.MULTILINE | re.DOTALL)
# What a title cannot hold in a link, which then names its page by the slug.
UNSAFE_RE = re.compile(r'[/|\[\]]')


def reference(written: str) -> str:
    """The address a link names, each part as a slug: "Engineering/Deploying" names
    "engineering/deploying". Empty when it names none."""
    return '/'.join(slug for slug in (slug_of(part) for part in written.split('/')) if slug)


def resolve(references: set[str]) -> dict[str, Page]:
    """The pages these addresses name, by address; addresses that name no page are left out."""
    references = {reference for reference in references if reference}
    fields = ('id', 'parent_id', 'title', 'slug', 'path')
    found = {page.path: page for page in Page.objects.filter(path__in=references).only(*fields)}
    rest = references - found.keys()
    if rest:
        formers = FormerPath.objects.filter(path__in=rest).select_related('page')
        found |= {former.path: former.page for former in formers.only('path', *(f'page__{f}' for f in fields))}
        rest -= found.keys()
    if rest:
        ends = Q()
        for end in rest:
            ends |= Q(path__endswith=f'/{end}')
        # The highest in the tree first.
        candidates = sorted(Page.objects.filter(ends).only(*fields), key=lambda page: (page.path.count('/'), page.path))
        for end in rest:
            page = next((page for page in candidates if page.path.endswith(f'/{end}')), None)
            if page is not None:
                found[end] = page
    return found


def _matches(text: str):
    """The links in `text`, but not those in code."""
    code = [match.span() for match in CODE_RE.finditer(text)]
    for match in LINK_RE.finditer(text):
        if not any(start <= match.start() < end for start, end in code):
            yield match


@dataclasses.dataclass(frozen=True)
class Missing:
    """What a link names that no page is, yet."""

    path: str
    title: str


class PageLinks(markdown.Reference):
    name = 'wiki_links'
    # Before the board's: "[[Release T-12]]" is one link, to the page.
    priority = 6
    pattern = LINK_RE
    classes: typing.ClassVar = {'a': {'wk-missing'}}

    def resolve(self, matches):
        written = {match: LINK_RE.fullmatch(match)[1] for match in matches}
        found = resolve({reference(text) for text in written.values()})
        result = {}
        for match, text in written.items():
            if path := reference(text):
                result[match] = found.get(path) or Missing(path, text.split('/')[-1].strip())
        return result

    def element(self, match, found):
        text, label = LINK_RE.fullmatch(match).groups()
        if isinstance(found, Missing):
            href = f'{reverse("gilde_wiki:page", args=[found.path])}?{urlencode({"title": found.title})}'
            link = ET.Element('a', {'href': href, 'class': 'wk-missing', 'title': _('No such page yet')})
            link.text = (label or text).strip()
        else:
            link = ET.Element('a', href=found.get_absolute_url())
            link.text = (label or '').strip() or found.title
        return link


def record(page: Page):
    """Keep the links in the page's text as they are now."""
    references = {reference(match[1]) for match in _matches(page.body)}
    references = {path for path in references if path and len(path) <= PATH_LENGTH}
    found = resolve(references)
    Link.objects.filter(source=page).delete()
    Link.objects.bulk_create(Link(source=page, reference=path, target=found.get(path)) for path in references)


def refresh(slugs: set[str]):
    """After pages got these slugs at a new address: the links that may name another page now, or one at
    last, are looked up again."""
    names = Q(target=None)
    for slug in slugs:
        names |= Q(reference=slug) | Q(reference__endswith=f'/{slug}')
    links = list(Link.objects.filter(names))
    found = resolve({link.reference for link in links})
    for link in links:
        link.target = found.get(link.reference)
    Link.objects.bulk_update(links, ['target'])


def follow(moved: dict[int, str]) -> set[int]:
    """After the pages `moved` (their old addresses by id) got new ones: the links to them in the wiki's
    pages name the new addresses. Each page so changed is saved, with a history record of its own. The
    ids of those pages."""
    targets = {}
    for link in Link.objects.filter(target__in=moved).select_related('target'):
        targets.setdefault(link.source_id, {})[link.reference] = link.target
    rewritten = set()
    for source in Page.objects.filter(pk__in=targets):
        body = _rewrite(source.body, targets[source.pk])
        if body != source.body:
            source.body = body
            source.save()
            rewritten.add(source.pk)
    return rewritten


def _rewrite(text: str, targets: dict[str, Page]) -> str:
    def replace(match):
        written, label = match.groups()
        old = reference(written)
        target = targets.get(old)
        if target is None:
            return match[0]
        new = spelling(target, parts=old.count('/') + 1, slugs=written.strip() == old)
        if reference(new) == old:
            return match[0]
        return f'[[{new}|{label}]]' if label is not None else f'[[{new}]]'

    pieces, last = [], 0
    for match in _matches(text):
        pieces += [text[last : match.start()], replace(match)]
        last = match.end()
    return ''.join(pieces) + text[last:]


def spelling(page: Page, parts: int = 1, slugs: bool = False) -> str:
    """How a link names `page`: the end of its address of at least `parts` parts that finds it, in titles
    or, if `slugs`, slugs. A title that gives another slug than its page's, or holds what a link cannot,
    is written as the slug."""
    chain = [*page.ancestors(), page]

    def part(each: Page) -> str:
        if slugs or UNSAFE_RE.search(each.title) or slug_of(each.title) != each.slug:
            return each.slug
        return each.title.strip()

    for count in range(min(parts, len(chain)), len(chain) + 1):
        written = '/'.join(part(each) for each in chain[-count:])
        if resolve({reference(written)}).get(reference(written)) == page:
            return written
    return page.path
