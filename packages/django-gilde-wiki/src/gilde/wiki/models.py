"""The wiki: pages in Markdown, in one tree, each at an address that follows the tree."""

import dataclasses
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from gilde.wiki import conf  # noqa: F401 - the wiki's settings, with their defaults

SLUG_LENGTH = 100
PATH_LENGTH = 500


@dataclasses.dataclass
class Node:
    """A page in the tree, with the pages under it."""

    page: 'Page'
    children: list['Node'] = dataclasses.field(default_factory=list)


class PageQuerySet(models.QuerySet):
    def tree(self) -> list[Node]:
        """These pages as a tree, from one query: the pages without a parent among them, each with the
        pages under it, in their order."""
        pages = list(self.only('id', 'parent_id', 'title', 'path', 'position'))
        nodes = {page.pk: Node(page) for page in pages}
        roots = []
        for page in pages:
            parent = nodes.get(page.parent_id)
            (parent.children if parent else roots).append(nodes[page.pk])
        return roots


def slug_of(title: str) -> str:
    """The slug a title gives, empty when it has no letters or digits."""
    return slugify(title)[:SLUG_LENGTH].strip('-')


def flatten(nodes: list[Node], depth: int = 0):
    """(page, depth) for each page of the tree, in the order the tree shows them."""
    for node in nodes:
        yield node.page, depth
        yield from flatten(node.children, depth + 1)


class Page(models.Model):
    """A page of the wiki. A page with pages under it is what elsewhere is a space or a folder.

    Its address is its `path`, the slugs of its ancestors and its own: "engineering/deploying". Saving
    keeps the slug after the title and the paths of the page and everything under it up to date; the
    addresses they had before keep leading to them (FormerPath), and links to them in other pages follow
    (gilde.wiki.links).
    """

    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('under'),
    )
    position = models.PositiveIntegerField(default=0, help_text='Its place among the pages beside it, lowest first.')
    title = models.CharField(_('title'), max_length=255)
    slug = models.SlugField(
        max_length=SLUG_LENGTH,
        editable=False,
        help_text='The title as the end of the address, unique among the pages beside it.',
    )
    path = models.CharField(max_length=PATH_LENGTH, unique=True, editable=False)
    body = models.TextField(_('text'), blank=True, default='', help_text=_('Markdown. [[Page title]] links to a page.'))
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='gilde_wiki_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(excluded_fields=['position', 'updated_at'])

    objects = PageQuerySet.as_manager()

    class Meta:
        ordering = ('position', 'title', 'id')
        # Who may use the wiki at all (gilde.core.people); granted to groups in the admin.
        permissions = (('use', 'Can use the wiki'),)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from gilde.wiki import links  # noqa: PLC0415 - links imports this module

        with transaction.atomic():
            before = Page.objects.filter(pk=self.pk).values_list('path', flat=True).first() if self.pk else None
            self.slug = self._free_slug()
            self.path = self._new_path(self.slug)
            # A page now at an address another one had takes it over.
            FormerPath.objects.filter(path=self.path).delete()
            super().save(*args, **kwargs)
            if before == self.path:
                links.record(self)
                return
            moved = self._move_descendants(before) if before else {}
            # Links to the moved pages follow them, from the links as they were recorded before.
            rewritten = links.follow(moved)
            if self.pk in rewritten:
                self.body = Page.objects.values_list('body', flat=True).get(pk=self.pk)
            else:
                links.record(self)
            links.refresh({self.slug} | set(Page.objects.filter(pk__in=moved).values_list('slug', flat=True)))

    def get_absolute_url(self):
        return reverse('gilde_wiki:page', args=[self.path])

    def ancestors(self) -> list['Page']:
        """The pages above this one, the top first."""
        parts = self.path.split('/')
        paths = ['/'.join(parts[:end]) for end in range(1, len(parts))]
        return sorted(Page.objects.filter(path__in=paths), key=lambda page: len(page.path))

    def descendants(self) -> PageQuerySet:
        """Every page under this one, however deep."""
        return Page.objects.filter(path__startswith=f'{self.path}/')

    def clean(self):
        if self.pk and self.parent_id and (self.parent_id == self.pk or self.parent.path.startswith(f'{self.path}/')):
            raise ValidationError({'parent': _('A page cannot go under itself or a page under it.')})
        deepest = max([len(path) for path in self.descendants().values_list('path', flat=True)] or [0])
        below = deepest - len(self.path) if self.pk and deepest else 0
        if len(self._new_path(self._free_slug())) + below > PATH_LENGTH:
            raise ValidationError(_('This page would be too deep in the tree, or its title too long, for an address.'))

    def _new_path(self, slug: str) -> str:
        return f'{self.parent.path}/{slug}' if self.parent else slug

    def _free_slug(self) -> str:
        """The title as a slug, with -2, -3 and so on when a page beside this one has it already. A page
        keeps its slug while its title gives the same one."""
        base = slug_of(self.title) or 'page'
        taken = set(Page.objects.filter(parent=self.parent_id).exclude(pk=self.pk).values_list('slug', flat=True))
        if self.slug and re.fullmatch(rf'{re.escape(base)}(-\d+)?', self.slug) and self.slug not in taken:
            return self.slug
        slug, number = base, 1
        while slug in taken:
            number += 1
            suffix = f'-{number}'
            slug = f'{base[: SLUG_LENGTH - len(suffix)]}{suffix}'
        return slug

    def _move_descendants(self, before: str) -> dict[int, str]:
        """After the page's address changed from `before`: the same for the pages under it, and every
        old address keeps leading to its page. The old addresses of this page and those under it, by id."""
        moved = list(Page.objects.filter(path__startswith=f'{before}/'))
        old_paths = {self.pk: before} | {page.pk: page.path for page in moved}
        FormerPath.objects.update_or_create(path=before, defaults={'page': self})
        for page in moved:
            old = page.path
            page.path = f'{self.path}{old[len(before) :]}'
            FormerPath.objects.update_or_create(path=old, defaults={'page': page})
        FormerPath.objects.filter(path__in=[page.path for page in moved]).delete()
        # Their own place in the tree did not change, so no history record of their own.
        Page.objects.bulk_update(moved, ['path'])
        return old_paths


class FormerPath(models.Model):
    """An address a page had before it, or a page above it, was renamed or moved. It still leads to the
    page, until a page takes that address."""

    path = models.CharField(max_length=PATH_LENGTH, unique=True)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='former_paths')

    def __str__(self):
        return f'{self.path} → {self.page.path}'


class Link(models.Model):
    """A link in a page's text to a page of the wiki, "[[Deploying]]", by the address it names
    (`reference`), and the page that is, if any: what a page lists as the pages that link to it, and
    what follows a page to its new address."""

    source = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='links')
    reference = models.CharField(max_length=PATH_LENGTH)
    target = models.ForeignKey(Page, on_delete=models.SET_NULL, null=True, blank=True, related_name='backlinks')

    class Meta:
        constraints = (models.UniqueConstraint(fields=('source', 'reference'), name='gilde_wiki_link_once'),)

    def __str__(self):
        return f'{self.source.path} → {self.reference}'
