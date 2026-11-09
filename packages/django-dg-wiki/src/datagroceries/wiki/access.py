"""What someone may do in the wiki, per page: the one place every page, form, API call and MCP tool asks,
so an agent never does more than its person may.

It asks the project's `People` (datagroceries.core.people.may), after `may_use`, about a page, or about
`TOP` for the top of the wiki: by default whoever may use the wiki may do everything. Every page is asked
about the same way, however deep; a project that gives rights to a part of the tree looks up the tree in
its `may` (`page.ancestors()`).

The wiki adds one rule of its own: reading a page needs read on the top and on every page above it, as
its address, its crumbs and the tree name them. Who may not read a page does not see it, nor the pages
under it: they are missing from the tree, searches and the API, their addresses are not found, and a link
to one shows as a page they cannot see.

The answers are remembered for the request, and a branch someone may not read is skipped whole, so the
tree costs one question per page they may read; none when the project does not restrict anything.
"""

import collections

from django.core.exceptions import PermissionDenied
from django.http import Http404

from datagroceries.core import history, people
from datagroceries.wiki.conf import SCOPE
from datagroceries.wiki.models import TOP, FormerPath, Page, Top, build_tree

READ, COMMENT, WRITE, MANAGE = people.RIGHTS


def _remembered(name: str) -> dict:
    """A dict kept on the request being served, for answers that hold while it lasts; a new one outside a
    request, as in a task."""
    request = history.current_request()
    return request.__dict__.setdefault(f'_dg_wiki_{name}', {}) if request is not None else {}


def _asked(user, right: str, where: Page | Top) -> bool:
    """The project's answer, remembered; by its address too, as a page moved during the request is
    somewhere else."""
    answers = _remembered('rights')
    key = (user.pk, right, where.pk, where.path)
    if key not in answers:
        answers[key] = people.may(user, right, where)
    return answers[key]


def _may(user, right: str, where: Page | Top, above: list) -> bool:
    if user is None or not people.may_use(user, SCOPE):
        return False
    return all(_asked(user, READ, each) for each in above) and _asked(user, right, where)


def _above(where: Page | Top) -> list:
    """What must be readable before `where` is: the top and the pages above it, which the page then keeps
    knowing until it is saved."""
    if not isinstance(where, Page):
        return []
    if 'known_ancestors' not in where.__dict__:
        where.known_ancestors = where.ancestors()
    return [TOP, *where.known_ancestors]


def may(user, right: str, where: Page | Top = TOP) -> bool:
    """Whether `user` has `right` on the page `where`, or at the top: there, and read above it."""
    return _may(user, right, where, _above(where))


def require(user, right: str, where: Page | Top = TOP):
    if not may(user, right, where):
        place = f'on {where.path}' if isinstance(where, Page) else 'at the top of the wiki'
        raise PermissionDenied(f'You may not {right} {place}.')


def rights(user, where: Page | Top = TOP) -> dict[str, bool]:
    """What `user` may do on `where`, by right, for a template: `can.write`."""
    above = _above(where)
    return {right: _may(user, right, where, above) for right in people.RIGHTS}


def visible_to(page: Page):
    """Whether a person may read `page`, as a function of them: for its text to mute the @-mentions of
    people who cannot see it (datagroceries.core.mentions)."""
    above = _above(page)
    return lambda user: _may(user, READ, page, above)


def readers(page: Page, users) -> list:
    """Those of `users` who may read `page`: who hear about it."""
    can_read = visible_to(page)
    return [user for user in users if user is not None and can_read(user)]


class _Wiki:
    """Every page, each knowing the pages above it, and which of them a person may not read."""

    def __init__(self, user):
        self.pages = list(Page.objects.defer('body'))
        under = collections.defaultdict(list)
        for page in self.pages:
            under[page.parent_id].append(page)
        self.hidden = set()

        def branch(page):
            yield page.pk
            for child in under[page.pk]:
                yield from branch(child)

        def walk(parent_id, chain):
            for page in under[parent_id]:
                page.known_ancestors = chain
                if _may(user, READ, page, []):
                    walk(page.pk, [*chain, page])
                else:
                    self.hidden.update(branch(page))

        if _may(user, READ, TOP, []):
            walk(None, [])
        else:
            self.hidden = {page.pk for page in self.pages}

    def readable(self) -> list[Page]:
        return [page for page in self.pages if page.pk not in self.hidden]


def _wiki(user) -> _Wiki | None:
    """What `user` may read of the wiki; None when they may read all of it, as by default."""
    if user is not None and people.may_use(user, SCOPE) and not people.restricts():
        return None
    known = _remembered('wiki')
    key = user.pk if user is not None else None
    if key not in known:
        known[key] = _Wiki(user)
    return known[key]


def forget():
    """After pages were made or moved: who may read what is worked out again."""
    _remembered('wiki').clear()


def hidden(user) -> set[int]:
    """The ids of the pages `user` may not read; all of them for no user, as outside a request."""
    wiki = _wiki(user)
    return wiki.hidden if wiki else set()


def pages(user, queryset=None):
    """The pages of `queryset`, by default all, that `user` may read."""
    queryset = Page.objects.all() if queryset is None else queryset
    return queryset.exclude(pk__in=hidden(user))


def tree(user) -> list:
    """The pages `user` may read, as the tree (models.Node)."""
    wiki = _wiki(user)
    return build_tree(wiki.readable()) if wiki else Page.objects.tree()


def writable(user) -> set[int]:
    """The ids of the pages `user` may write on: change, and put pages under."""
    wiki = _wiki(user)
    if wiki is None:
        return set(Page.objects.values_list('pk', flat=True))
    return {page.pk for page in wiki.readable() if _may(user, WRITE, page, [])}


def page(user, path: str, queryset=None) -> Page:
    """The page at `path` that `user` may read; not found otherwise, whether it is there or not."""
    found = (queryset if queryset is not None else Page.objects.select_related('parent')).filter(path=path).first()
    if found is None or not may(user, READ, found):
        raise Http404(f'No page {path}.')
    return found


def former(user, path: str) -> Page | None:
    """The page that once was at `path`, if `user` may read it."""
    found = FormerPath.objects.select_related('page').filter(path=path).first()
    return found.page if found is not None and may(user, READ, found.page) else None
