"""Ticket tracker: groups with their own kanban columns, tickets, relations, comments and attachments."""

import datetime
import re
import typing

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, F, Q, When
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from datagroceries.board import conf  # noqa: F401 - the board's settings, with their defaults
from datagroceries.core import attachments

KEY_RE = re.compile(rf'^{re.escape(settings.DG_BOARD_KEY_PREFIX)}-(\d+)$')
# Room between neighbouring ranks: a ticket moved between two others takes the middle, so 16 moves
# into the same spot fit before the tickets are renumbered.
RANK_GAP = 2**16


class Group(models.Model):
    """A board: any set of tickets that shares a workflow, e.g. a team or a project."""

    name = models.CharField(_('name'), max_length=100, unique=True)
    slug = models.SlugField(_('slug'), max_length=100, unique=True)
    position = models.PositiveIntegerField(
        _('position'), default=0, help_text=_('Order of the group in the group switcher.')
    )
    done_days = models.PositiveSmallIntegerField(
        _('days done tickets stay on the board'),
        default=14,
        help_text=_('Counted from when a ticket entered a done column. Its page stays either way.'),
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ('position', 'name')

    def __str__(self):
        return self.name

    def matching_column(self, column: 'Column') -> 'Column | None':
        """The column here that a ticket in `column` moves to: the same name, else the same category,
        else the first. "Won't do" stays "Won't do" rather than joining "Done". None without columns."""
        columns = list(self.columns.all())
        same_name = [c for c in columns if c.name.lower() == column.name.lower()]
        same_category = [c for c in columns if c.category == column.category]
        return (same_name or same_category or columns or [None])[0]

    def intake_column(self) -> 'Column | None':
        """Where a new ticket goes unless told otherwise: the to-do column nearest the work, so "To do"
        rather than an "Icebox" in front of it. None without columns."""
        columns = list(self.columns.all())
        first_work = next((i for i, c in enumerate(columns) if c.category != Column.Category.TODO), len(columns))
        todo = columns[:first_work] or [c for c in columns if c.category == Column.Category.TODO] or columns
        return todo[-1] if todo else None


class Column(models.Model):
    """A kanban column of one group. Its category is what "open" or "done" means across groups."""

    class Category(models.TextChoices):
        TODO = 'todo', _('To do')
        IN_PROGRESS = 'in_progress', _('In progress')
        DONE = 'done', _('Done')

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='columns')
    name = models.CharField(_('name'), max_length=100)
    category = models.CharField(_('category'), max_length=20, choices=Category.choices)
    position = models.PositiveIntegerField(_('position'), default=0)
    history = HistoricalRecords()

    class Meta:
        ordering = ('group__position', 'group__name', 'position', 'id')
        constraints = (models.UniqueConstraint(fields=('group', 'name'), name='dg_board_column_unique_name'),)

    def __str__(self):
        return self.name


class Label(models.Model):
    """A free-form tag. Global rather than per group, so labels stay on a ticket that changes group."""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class TicketQuerySet(models.QuerySet):
    def search(self, query: str) -> 'TicketQuerySet':
        """The tickets `query` finds, best first: the one it is the key of (T-831, or 831 alone), then
        those with it in the title, then those with it only in the description; newest first within
        each. search_rank on each says which (0, 1 or 2).

        The one search behind the board, the relation picker and the API.
        """
        query = query.strip()
        if not query:
            return self.none()
        key_match = KEY_RE.match(query.upper())
        pk = int(key_match[1]) if key_match else int(query) if query.isdigit() else None
        in_title = Q(title__icontains=query)
        return (
            self.filter(Q(pk=pk) | in_title | Q(description__icontains=query))
            .annotate(search_rank=Case(When(pk=pk, then=0), When(in_title, then=1), default=2))
            .order_by('search_rank', '-pk')
        )

    def on_board(self) -> 'TicketQuerySet':
        """The tickets a board shows: all but those done longer ago than their group's done_days."""
        # A condition per group rather than done_days times a day in SQL, which SQLite cannot do.
        now = timezone.now()
        gone = Q(pk__in=[])
        for group in Group.objects.only('done_days'):
            gone |= Q(column__group=group, closed_at__lt=now - datetime.timedelta(days=group.done_days))
        return self.exclude(gone)


class Ticket(models.Model):
    """A unit of work. Its key is the prefix plus the primary key, so it never changes with the group."""

    class Size(models.TextChoices):
        HOURS = 'hours', _('Hours')
        DAYS = 'days', _('Days')
        WEEKS = 'weeks', _('Weeks')
        MONTHS = 'months', _('Months')
        UNKNOWN = 'unknown', _('Unknown')

    title = models.CharField(_('title'), max_length=255)
    description = models.TextField(_('description'), blank=True, default='', help_text=_('Markdown.'))
    column = models.ForeignKey(
        Column,
        on_delete=models.PROTECT,
        related_name='tickets',
        help_text='The group follows from the column: moving to another group means picking one of its columns.',
    )
    rank = models.BigIntegerField(
        default=0,
        help_text='Place in the one order of all tickets, lowest first; a column shows its tickets in this order.',
    )
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='dg_board_created')
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dg_board_assigned',
        verbose_name=_('assignee'),
    )
    size = models.CharField(
        _('size'),
        max_length=10,
        choices=Size.choices,
        blank=True,
        default='',
        help_text=_('Empty means not estimated yet; "unknown" means estimated and impossible to tell.'),
    )
    labels = models.ManyToManyField(Label, blank=True, related_name='tickets')
    is_blocked = models.BooleanField(
        default=False,
        help_text='Set and cleared together with a comment that says why (Comment.sets_blocked).',
    )
    closed_at = models.DateTimeField(null=True, blank=True, help_text='When the ticket entered a done column.')
    # Also the date of the first history record, but read on every board and page.
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords(m2m_fields=[labels], excluded_fields=['rank'])

    objects = TicketQuerySet.as_manager()

    class Meta:
        ordering = ('rank', 'id')
        # Who may use the board at all (datagroceries.core.people); granted to groups in the admin.
        permissions = (('use', 'Can use the board'),)

    def __str__(self):
        return f'{self.key} {self.title}'

    def save(self, *args, **kwargs):
        if self.column.category == Column.Category.DONE:
            self.closed_at = self.closed_at or timezone.now()
        else:
            self.closed_at = None
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('dg_board:ticket_detail', args=[self.key])

    @property
    def key(self) -> str:
        return f'{settings.DG_BOARD_KEY_PREFIX}-{self.pk}'

    def move_to(self, column: Column, *, before: 'Ticket | None' = None, after: 'Ticket | None' = None):
        """Put the ticket in `column`, just above `before` or just below `after` in the order of all
        tickets, and save it. With neither it keeps its place, and a new ticket goes last.

        Only a change of column is saved with a history record; a new place alone is not.
        """
        if before is not None and after is not None:
            raise ValueError('Place a ticket above one ticket or below one, not both.')
        with transaction.atomic():
            if before is not None or after is not None:
                self.rank = self._free_rank(before, after)
            elif self.pk is None:
                last = Ticket.objects.last()
                self.rank = last.rank + RANK_GAP if last else RANK_GAP
            if self.pk is not None and self.column_id == column.pk:
                Ticket.objects.filter(pk=self.pk).update(rank=self.rank)
                return
            self.column = column
            self.save()

    def _free_rank(self, before: 'Ticket | None', after: 'Ticket | None') -> int:
        """A rank between `before` or `after` and its neighbour in the order of all tickets.

        Ranks leave gaps, so a move changes one rank. When a gap is used up, every ticket is
        renumbered with bulk_update, which bypasses simple_history.
        """
        others = Ticket.objects.exclude(pk=self.pk)
        for _attempt in range(2):
            if before is not None:
                high = others.get(pk=before.pk).rank
                neighbour = others.filter(Q(rank__lt=high) | Q(rank=high, pk__lt=before.pk)).last()
                low = neighbour.rank if neighbour else high - 2 * RANK_GAP
            else:
                low = others.get(pk=after.pk).rank
                neighbour = others.filter(Q(rank__gt=low) | Q(rank=low, pk__gt=after.pk)).first()
                high = neighbour.rank if neighbour else low + 2 * RANK_GAP
            if high - low > 1:
                return (low + high) // 2
            ordered = list(Ticket.objects.select_for_update().only('rank').order_by('rank', 'id'))
            for position, ticket in enumerate(ordered, start=1):
                ticket.rank = position * RANK_GAP
            Ticket.objects.bulk_update(ordered, ['rank'], batch_size=1000)
        raise AssertionError(f'No free rank next to {before or after} after renumbering every ticket.')

    def open_blockers(self) -> models.QuerySet:
        """Tickets that block this one and are not done yet."""
        return Ticket.objects.filter(
            outgoing_relations__target=self,
            outgoing_relations__type=Relation.Type.BLOCKS,
        ).exclude(column__category=Column.Category.DONE)


class Relation(models.Model):
    """A directed link between two tickets, read as "source <type> target".

    Parent/child is a relation like any other, with one extra rule: a ticket has at most one parent.
    """

    class Type(models.TextChoices):
        PARENT_OF = 'parent_of', _('parent of')
        DUPLICATE_OF = 'duplicate_of', _('duplicate of')
        BLOCKS = 'blocks', _('blocks')
        RELATES_TO = 'relates_to', _('relates to')

    # How the relation reads from the target's side.
    INVERSE_LABELS: typing.ClassVar = {
        Type.PARENT_OF: _('child of'),
        Type.DUPLICATE_OF: _('duplicated by'),
        Type.BLOCKS: _('blocked by'),
        Type.RELATES_TO: _('relates to'),
    }
    # Types in which following the arrow must never lead back to where it started.
    ACYCLIC_TYPES = (Type.PARENT_OF, Type.BLOCKS)

    source = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='outgoing_relations')
    target = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='incoming_relations')
    type = models.CharField(max_length=20, choices=Type.choices)
    # Who added it and when is in its history.
    history = HistoricalRecords()

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=('source', 'target', 'type'), name='dg_board_relation_unique'),
            models.UniqueConstraint(
                fields=('target',),
                condition=Q(type='parent_of'),
                name='dg_board_relation_one_parent',
                violation_error_message='A ticket can have only one parent.',
            ),
            models.CheckConstraint(condition=~Q(source=F('target')), name='dg_board_relation_not_to_itself'),
        )

    def __str__(self):
        return f'{self.source.key} {self.get_type_display()} {self.target.key}'

    def clean(self):
        if self.type not in self.ACYCLIC_TYPES or self.source_id == self.target_id:
            return
        # Walk the arrows of this type onward from the target; reaching the source closes a loop.
        frontier = {self.target_id}
        seen = set()
        while frontier:
            if self.source_id in frontier:
                raise ValidationError(
                    _('This would make a loop of "%(type)s" relations.') % {'type': self.get_type_display()}
                )
            seen |= frontier
            frontier = (
                set(
                    Relation.objects.filter(source_id__in=frontier, type=self.type).values_list('target_id', flat=True),
                )
                - seen
            )


class Comment(models.Model):
    """A comment on a ticket, or a reply to one. Replies go one level deep."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ticket_comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    body = models.TextField(_('comment'), help_text=_('Markdown.'))
    sets_blocked = models.BooleanField(
        null=True,
        blank=True,
        help_text='True if this comment blocked the ticket, False if it unblocked it; empty for a plain comment.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ('created_at', 'id')

    def __str__(self):
        return f'Comment {self.pk} on {self.ticket.key}'

    def clean(self):
        if self.parent is not None and self.parent.parent_id is not None:
            raise ValidationError(_('A reply cannot be replied to; reply to the comment above it instead.'))
        if self.parent is not None and self.parent.ticket_id != self.ticket_id:
            raise ValidationError(_('A reply must be on the same ticket as its comment.'))


class Watcher(models.Model):
    """Someone who hears about a ticket (notifications.py). Creator, assignee, commenters and people @-mentioned
    watch automatically; anyone can start or stop watching on the ticket page."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='watchers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watched_tickets')

    class Meta:
        constraints = (models.UniqueConstraint(fields=('ticket', 'user'), name='dg_board_watcher_unique'),)

    def __str__(self):
        return f'{self.user} watches {self.ticket.key}'


class CodeReference(models.Model):
    """Something in the code repository that mentions a ticket's key: a commit on the default branch, and
    in time a branch or a pull request. Recorded by the GitHub webhook or the backfill (tickets/github.py).
    """

    class Kind(models.TextChoices):
        COMMIT = 'commit', _('Commit')
        BRANCH = 'branch', _('Branch')
        PULL_REQUEST = 'pull_request', _('Pull request')

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='code_references')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    ref = models.CharField(max_length=255, help_text="A commit's sha, a branch's name or a pull request's number.")
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=300, help_text="A commit message's first line, or the pull request's title.")
    author = models.CharField(max_length=200, help_text='The name git or GitHub has for the author.')
    state = models.CharField(max_length=20, blank=True, help_text='For a pull request: open, merged or closed.')
    happened_at = models.DateTimeField(
        help_text='When the commit was made, the branch pushed or the pull request opened.',
    )

    class Meta:
        ordering = ('-happened_at',)
        constraints = (models.UniqueConstraint(fields=('ticket', 'kind', 'ref'), name='dg_board_codereference_unique'),)

    def __str__(self):
        return f'{self.get_kind_display()} {self.ref[:12]} on {self.ticket.key}'


class Attachment(attachments.Attachment):
    """A file on a ticket. Images pasted into the editor are uploaded before the ticket may exist,
    so the ticket is linked once the description that references it is saved."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments')

    def get_absolute_url(self):
        return reverse('dg_board:attachment_file', args=[self.pk, self.url_name])
