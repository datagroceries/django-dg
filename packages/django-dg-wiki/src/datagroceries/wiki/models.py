"""The wiki: pages in Markdown, in one tree, each at an address that follows the tree."""

import dataclasses
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords
from simple_history.signals import pre_create_historical_record

from datagroceries.core import attachments
from datagroceries.wiki import conf  # noqa: F401 - the wiki's settings, with their defaults

SLUG_LENGTH = 100
PATH_LENGTH = 500


@dataclasses.dataclass
class Node:
    """A page in the tree, with the pages under it."""

    page: 'Page'
    children: list['Node'] = dataclasses.field(default_factory=list)


def build_tree(pages: list['Page']) -> list[Node]:
    """`pages`, in their order, as a tree: the pages without a parent among them, each with the pages
    under it."""
    nodes = {page.pk: Node(page) for page in pages}
    roots = []
    for page in pages:
        parent = nodes.get(page.parent_id)
        (parent.children if parent else roots).append(nodes[page.pk])
    return roots


class PageQuerySet(models.QuerySet):
    def tree(self) -> list[Node]:
        """These pages as a tree, from one query."""
        return build_tree(list(self.only('id', 'parent_id', 'title', 'path', 'folder', 'position', 'language')))


def slug_of(title: str) -> str:
    """The slug a title gives, empty when it has no letters or digits."""
    return slugify(title)[:SLUG_LENGTH].strip('-')


def flatten(nodes: list[Node], depth: int = 0):
    """(page, depth) for each page of the tree, in the order the tree shows them."""
    for node in nodes:
        yield node.page, depth
        yield from flatten(node.children, depth + 1)


class Version(models.Model):
    """What each version of a page keeps besides the page's own fields."""

    restored_from = models.PositiveBigIntegerField(
        null=True, blank=True, help_text='The version this one brought back, by its history_id.'
    )

    class Meta:
        abstract = True


class Top:
    """The wiki's top, above every page: whoever may write here may make a page at the top
    (datagroceries.wiki.access). There is one, `TOP`."""

    pk = None
    path = ''

    def __str__(self):
        return str(settings.DG_WIKI_NAME)

    def __repr__(self):
        return '<the top of the wiki>'

    def ancestors(self) -> list:
        return []


TOP = Top()


class Page(models.Model):
    """A page of the wiki: a page of its own, or a folder, whose text is its index and which may have pages
    under it, as files and folders are. Only a folder has pages under it; a page becomes one, or a folder
    with none under it a page, only when someone says so (operations.make_folder).

    Its address is its `path`, the slugs of its ancestors and its own: "engineering/deploying". On the site a
    folder's ends in "/" and a page's does not, so a relative link lands in a browser where it does in the
    wiki: in the folder it is written in (`folder_path`, datagroceries.wiki.links). Saving
    keeps the slug after the title and the paths of the page and everything under it up to date; the
    addresses they had before keep leading to them (FormerPath), and links to them in other pages follow
    (datagroceries.wiki.links).
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
    folder = models.BooleanField(_('folder'), default=False, help_text='A folder of pages, its text their index.')
    body = models.TextField(_('text'), blank=True, default='', help_text=_('Markdown. [[Page title]] links to a page.'))
    language = models.CharField(
        _('language'), max_length=10, blank=True, help_text='One of settings.LANGUAGES, or empty when it says none.'
    )
    original = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='translations',
        help_text='The page this one translates; the translations of a page all name the same original.',
    )
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='dg_wiki_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(excluded_fields=['position', 'updated_at'], bases=[Version])

    objects = PageQuerySet.as_manager()

    class Meta:
        ordering = ('position', 'title', 'id')
        # Who may use the wiki at all (datagroceries.core.people); granted to groups in the admin.
        permissions = (('use', 'Can use the wiki'),)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from datagroceries.wiki import links  # noqa: PLC0415 - links imports this module

        # It may be somewhere else now.
        self.__dict__.pop('known_ancestors', None)
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
            links.refresh({self.path} | set(Page.objects.filter(pk__in=moved).values_list('path', flat=True)))

    def get_absolute_url(self):
        return reverse('dg_wiki:folder' if self.folder else 'dg_wiki:page', args=[self.path])

    @property
    def folder_path(self) -> str:
        """The address of the folder the page is in, or that it is: where its links start. Empty at the top."""
        return self.path if self.folder else self.path.rpartition('/')[0]

    def ancestors(self) -> list['Page']:
        """The pages above this one, the top first."""
        if (known := self.__dict__.get('known_ancestors')) is not None:  # from the tree access.py loaded
            return known
        parts = self.path.split('/')
        paths = ['/'.join(parts[:end]) for end in range(1, len(parts))]
        return sorted(Page.objects.filter(path__in=paths), key=lambda page: len(page.path))

    def translation_group(self) -> list['Page']:
        """The page in every language it is in: the original first, then its translations."""
        original = self.original or self
        return [original, *original.translations.order_by('language', 'pk')]

    def descendants(self) -> PageQuerySet:
        """Every page under this one, however deep."""
        return Page.objects.filter(path__startswith=f'{self.path}/')

    def clean(self):
        if self.pk and self.parent_id and (self.parent_id == self.pk or self.parent.path.startswith(f'{self.path}/')):
            raise ValidationError({'parent': _('A page cannot go under itself or a page under it.')})
        if self.parent_id and not self.parent.folder:
            raise ValidationError(
                {'parent': _('“%(title)s” is a page, not a folder: make it a folder first.') % {'title': self.parent}}
            )
        if not self.folder and self.pk and self.children.exists():
            raise ValidationError(_('Only a folder has pages in it: move or delete them first.'))
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
        constraints = (models.UniqueConstraint(fields=('source', 'reference'), name='dg_wiki_link_once'),)

    def __str__(self):
        return f'{self.source.path} → {self.reference}'


@receiver(pre_create_historical_record)
def _note_restore(sender, instance, history_instance, **kwargs):
    # Sent by the history model of every model with a history, so not filtered by sender.
    if isinstance(instance, Page):
        history_instance.restored_from = getattr(instance, 'restored_from', None)


class Attachment(attachments.Attachment):
    """A file on a page: an image in its text, or a file beside it."""

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='attachments')

    def get_absolute_url(self):
        return reverse('dg_wiki:attachment', args=[self.pk, self.url_name])


class Comment(models.Model):
    """A comment on a page, or a reply to one. Replies go one level deep."""

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='dg_wiki_comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    body = models.TextField(_('comment'))
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ('created_at', 'id')

    def __str__(self):
        return f'Comment {self.pk} on {self.page.path}'

    def get_absolute_url(self):
        return f'{self.page.get_absolute_url()}#comment-{self.pk}'

    def clean(self):
        if self.parent is not None and self.parent.parent_id is not None:
            raise ValidationError(_('A reply cannot be replied to; reply to the comment above it instead.'))
        if self.parent is not None and self.parent.page_id != self.page_id:
            raise ValidationError(_('A reply must be on the same page as its comment.'))


class Watcher(models.Model):
    """Someone who hears about the comments on a page (notifications.py). Its creator, the people who
    write it or comment on it, and the people @-mentioned in it watch it of themselves; anyone can start
    or stop watching on the page."""

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='watchers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='dg_wiki_watched')

    class Meta:
        constraints = (models.UniqueConstraint(fields=('page', 'user'), name='dg_wiki_watcher_once'),)

    def __str__(self):
        return f'{self.user} watches {self.page.path}'
