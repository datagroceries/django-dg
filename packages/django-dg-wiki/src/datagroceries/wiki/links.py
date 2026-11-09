"""Links to wiki pages: "[[Rollback]]" links to the page Rollback in the folder it is written in, and
"[[Rollback|how we go back]]" does with words of its own, in every DataGroceries app's Markdown while the wiki
is installed (datagroceries.core.markdown), so a ticket can link to a page too.

A link names a page by its address, written in titles or in slugs: "Deploying/Rollback" and
"deploying/rollback" are the same. It starts in the folder it is written in (Page.folder_path), as a browser
finds a relative address: on the folder "engineering", "[[International]]" and "[[./International]]" are
"engineering/international", in it; on the page "engineering/platform", "[[Algorithms]]" is
"engineering/algorithms", beside it, in the same folder. "[[International/Belgium]]" goes further down, and
"[[../Sales]]" one folder up: each ".." is one level. A link that starts with "/" is from the top of the wiki:
"[[/Sales/Q4]]". Nothing else is looked for: a link names one address, never a page somewhere else in the
tree. Outside a wiki page, as in a ticket, only a link from the top is one; any other stays text. A "/" at
the end changes nothing: "[[Sales/]]" is "[[Sales]]". An address a page had before a rename or a move still
finds it. A link to no page shows as one, and leads to where that page can be started. A link to a page the
reader may not see (datagroceries.wiki.access) shows as one, by the name written, not its title, and leads
nowhere.

The wiki keeps the links in its own pages (Link): to list what links to a page, and to rewrite them when
a page they name, or the page they are in, gets another address, so they keep saying where the page is, in
the way they were written.
"""

import dataclasses
import re
import typing
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from datagroceries.core import history, markdown
from datagroceries.wiki import access
from datagroceries.wiki.models import PATH_LENGTH, FormerPath, Link, Page, Top, slug_of

LINK_RE = re.compile(r'\[\[([^\[\]|\n]+)(?:\|([^\[\]\n]+))?\]\]')
# Fenced and inline code, where "[[...]]" is text as written, as Markdown shows it.
CODE_RE = re.compile(r'^(```|~~~).*?^\1|`[^`\n]+`', re.MULTILINE | re.DOTALL)
# What a title cannot hold in a link, which then names its page by the slug.
UNSAFE_RE = re.compile(r'[/|\[\]]')


RELATIVE = ('.', '..')


def reference(written: str, base: str | None = None) -> str:
    """The address a link names, from the top, each part as a slug: "/engineering/deploying". From the top
    when it starts with "/"; else from `base`, the address of the page it is in: "Rollback" and
    "./Rollback" in the page "engineering/deploying" name "/engineering/deploying/rollback", and
    "../Onboarding" names "/engineering/onboarding". Empty when it names none: a relative link without a
    page to start from, as in a ticket, or one that goes above the top."""
    written = written.strip()
    if written.startswith('/'):
        slugs = []
    elif base is None:
        return ''
    else:
        slugs = base.split('/') if base else []
    for part in written.split('/'):
        if part.strip() == '..':
            if not slugs:
                return ''
            slugs.pop()
        elif part.strip() != '.' and (slug := slug_of(part)):
            slugs.append(slug)
    return f'/{"/".join(slugs)}' if slugs else ''


def name(written: str) -> str:
    """The name a link shows for a page that is not there yet: the last part of what was written,
    "Sales" for "Sales/" too. Empty when it has none, as "..", which names a page by where it is only."""
    parts = (part.strip() for part in reversed(written.split('/')))
    return next((part for part in parts if part and part not in RELATIVE), '')


def resolve(references: set[str]) -> dict[str, Page]:
    """The pages these addresses, as `reference` gives them, name, by address; addresses that name no page
    are left out."""
    references = {reference for reference in references if reference}
    paths = {reference.removeprefix('/') for reference in references}
    fields = ('id', 'parent_id', 'title', 'path', 'folder')
    at = {page.path: page for page in Page.objects.filter(path__in=paths).only(*fields)}
    if rest := paths - at.keys():
        formers = FormerPath.objects.filter(path__in=rest).select_related('page')
        at |= {former.path: former.page for former in formers.only('path', *(f'page__{f}' for f in fields))}
    return {reference: at[reference.removeprefix('/')] for reference in references if reference.removeprefix('/') in at}


def matches(text: str):
    """The links in `text`, but not those in code."""
    code = [match.span() for match in CODE_RE.finditer(text)]
    for match in LINK_RE.finditer(text):
        if not any(start <= match.start() < end for start, end in code):
            yield match


def substitute(text: str, replace) -> str:
    """`text` with each link outside code replaced by what `replace(match)` makes of it."""
    pieces, last = [], 0
    for match in matches(text):
        pieces += [text[last : match.start()], replace(match)]
        last = match.end()
    return ''.join(pieces) + text[last:]


@dataclasses.dataclass(frozen=True)
class Missing:
    """What a link names that no page is, yet."""

    path: str
    title: str


@dataclasses.dataclass(frozen=True)
class Hidden:
    """A page the reader may not see, by the name the link gave it."""

    title: str


class PageLinks(markdown.Reference):
    name = 'wiki_links'
    # Before the board's: "[[Release T-12]]" is one link, to the page.
    priority = 6
    pattern = LINK_RE
    classes: typing.ClassVar = {'a': {'wk-missing'}, 'span': {'wk-hidden'}}
    help_heading = gettext_lazy('Links to wiki pages')

    @classmethod
    def help(cls):
        # The page names in an example and in what it says are translated alike.
        return [
            (
                _('[[Platform]]'),
                _(
                    'On a folder: the page Platform in it. A link starts in the folder it is written in, as an '
                    'address does in a browser.'
                ),
            ),
            (_('[[Platform]]'), _('On a page of its own: the page Platform beside it, in the same folder.')),
            (_('[[Platform/Testing]]'), _('Further down: the page Testing, in the folder Platform.')),
            (_('[[../Sales]]'), _('Sales, one folder up. Each ../ goes one level up.')),
            (
                _('[[/Engineering/Deploying]]'),
                _(
                    'From the top of the wiki: Deploying, in Engineering. Outside the wiki, as in a ticket, '
                    'only these work.'
                ),
            ),
            (_('[[Platform|our platform]]'), _('A link with words of your own.')),
            (_('[[New page]]'), _('A page that is not there yet shows red. Following the link starts it.')),
        ]

    def resolve(self, matches):
        page = self.context.get('wiki_page')
        base = page.folder_path if isinstance(page, Page | Top) else None
        names = {match: reference(LINK_RE.fullmatch(match)[1], base) for match in matches}
        found = resolve(set(names.values()))
        # Who reads it: the person the page being served is for; nobody outside a request.
        request = history.current_request()
        hidden = access.hidden(request.user if request else None)
        result = {}
        for match, path in names.items():
            if path in found and found[path].pk in hidden:
                result[match] = Hidden(name(LINK_RE.fullmatch(match)[1]) or match)
            elif path in found:
                result[match] = found[path]
            # A link to no page with no name to show stays text, as written, rather than show as nothing.
            elif path and (title := name(LINK_RE.fullmatch(match)[1])):
                result[match] = Missing(path.removeprefix('/'), title)
        return result

    def element(self, match, found):
        label = (LINK_RE.fullmatch(match)[2] or '').strip()
        if isinstance(found, Missing):
            href = f'{reverse("dg_wiki:page", args=[found.path])}?{urlencode({"title": found.title})}'
            link = ET.Element('a', {'href': href, 'class': 'wk-missing', 'title': _('No such page yet')})
            # As a link to a page shows its title: the name, not the way there.
            link.text = label or found.title
        elif isinstance(found, Hidden):
            link = ET.Element('span', {'class': 'wk-hidden', 'title': _('A page you cannot see')})
            link.text = label or found.title
        else:
            link = ET.Element('a', href=found.get_absolute_url())
            link.text = label or found.title
        return link


def record(page: Page):
    """Keep the links in the page's text as they are now."""
    references = {reference(match[1], page.folder_path) for match in matches(page.body)}
    references = {path for path in references if path and len(path) <= PATH_LENGTH}
    found = resolve(references)
    Link.objects.filter(source=page).delete()
    Link.objects.bulk_create(Link(source=page, reference=path, target=found.get(path)) for path in references)


def refresh(paths: set[str]):
    """After pages got these addresses: the links that name them, which may have named another page or
    none, are looked up again."""
    links = list(Link.objects.filter(reference__in=[f'/{path}' for path in paths]))
    found = resolve({link.reference for link in links})
    for link in links:
        link.target = found.get(link.reference)
    Link.objects.bulk_update(links, ['target'])


def follow(moved: dict[int, str]) -> set[int]:
    """After the pages `moved` (their old addresses by id) got new ones: the links in the wiki's pages
    that named them, and the relative links in the moved pages themselves, say where their pages are now.
    Each page so changed is saved, with a history record of its own. The ids of those pages."""
    targets = {}
    links = Link.objects.filter(Q(target__in=moved) | Q(source__in=moved)).exclude(target=None)
    for link in links.select_related('target'):
        targets.setdefault(link.source_id, {})[link.reference] = link.target
    rewritten = set()
    for source in Page.objects.filter(pk__in=targets):
        before = moved.get(source.pk, source.path)
        before = before if source.folder else before.rpartition('/')[0]
        body = _rewrite(source.body, targets[source.pk], before=before, now=source.folder_path)
        if body != source.body:
            source.body = body
            source.save()
            rewritten.add(source.pk)
    return rewritten


def _rewrite(text: str, targets: dict[str, Page], before: str, now: str) -> str:
    """`text`, of a page in the folder `now`, that was in `before` when its links named `targets`, with each
    link naming its page as it is now, written the way it was."""

    def replace(match):
        written, label = match.groups()
        target = targets.get(reference(written, before))
        if target is None:
            return match[0]
        new = spelling(target, written, now)
        if reference(new, now) == reference(written, now):
            return match[0]
        return f'[[{new}|{label}]]' if label is not None else f'[[{new}]]'

    return substitute(text, replace)


def spelling(page: Page, written: str = '', base: str | None = None) -> str:
    """How a link names `page`, the way `written`, a link to it, was written: from the top ("/..."), or from
    `base`, the address of the page it is in ("Rollback", "./Rollback", "../Onboarding"); in titles or, if
    `written` was in slugs, slugs. A title that holds what a link cannot, as "CI/CD", is written as its slug."""
    # A "/" at the end, or one too many between, is no part.
    parts = [part.strip() for part in written.strip().removeprefix('/').split('/') if part.strip()]
    slugs = bool(parts) and all(part in RELATIVE or part == slug_of(part) for part in parts)
    chain = [*page.ancestors(), page]

    def spelled(pages: list[Page]) -> list[str]:
        return [each.slug if slugs or UNSAFE_RE.search(each.title) else each.title.strip() for each in pages]

    if written.strip().startswith('/') or base is None:
        return '/' + '/'.join(spelled(chain))
    here, there = (base.split('/') if base else []), page.path.split('/')
    shared = 0
    while shared < min(len(here), len(there)) and here[shared] == there[shared]:
        shared += 1
    up = ['..'] * (len(here) - shared)
    if not up and parts[:1] == ['.']:
        up = ['.']
    return '/'.join(up + spelled(chain[shared:])) or '.'


def rebase(text: str, before: str, now: str) -> str:
    """`text`, whose relative links started from the folder `before`, with each naming the same address
    from the folder `now`, written in titles where it was; links from the top stay as they are."""

    def replace(match):
        written, label = match.groups()
        address = reference(written, before)
        if written.strip().startswith('/') or not address or reference(written, now) == address:
            return match[0]
        here, there = (now.split('/') if now else []), address.removeprefix('/').split('/')
        shared = 0
        while shared < min(len(here), len(there)) and here[shared] == there[shared]:
            shared += 1
        below = there[shared:]
        named = [part.strip() for part in written.split('/') if part.strip() and part.strip() not in RELATIVE]
        if len(named) >= len(below):
            below = [
                name if slug_of(name) == slug else slug
                for name, slug in zip(named[len(named) - len(below) :], below, strict=True)
            ]
        new = '/'.join(['..'] * (len(here) - shared) + below) or '.'
        return f'[[{new}|{label}]]' if label is not None else f'[[{new}]]'

    return substitute(text, replace)
