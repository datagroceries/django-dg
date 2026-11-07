"""The activity feed on a ticket page: field changes, relation changes and comments, newest first."""

import dataclasses
import datetime

from django.db.models import Prefetch, Q
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from simple_history.models import DeletedObject

from datagroceries.board.models import Column, Comment, Group, Relation, Ticket
from datagroceries.core import people

# Fields whose change is not worth a line: bookkeeping, or shown another way (blocked has its comment).
QUIET_FIELDS = ('closed_at', 'is_blocked')
# Bootstrap icon for an entry, by the first field it changed.
FIELD_ICONS = {
    'title': 'bi-pencil',
    'description': 'bi-text-left',
    'column': 'bi-arrow-right-circle',
    'assignee': 'bi-person',
    'size': 'bi-hourglass-split',
    'labels': 'bi-tag',
}


@dataclasses.dataclass
class Entry:
    when: datetime.datetime
    user: object
    lines: list[str] = dataclasses.field(default_factory=list)
    comment: Comment | None = None
    # Who to name when there is no user, e.g. a change written by an import command.
    fallback: str = gettext_lazy('Someone')
    icon: str = 'bi-dot'
    # "via Claude Code on my laptop" when made with an API token.
    via: str = ''


def _via(record) -> str:
    """The history keeps "via Claude Code on my laptop" in English; it shows in the reader's language."""
    reason = record.history_change_reason or ''
    return _('via %(name)s') % {'name': reason.removeprefix('via ')} if reason.startswith('via ') else ''


def _person(user) -> str:
    if isinstance(user, DeletedObject):
        return _('a deleted user')
    return people.name(user) if user else _('nobody')


def _last_version(model, pk):
    """The last history record of a row, which outlives the row itself."""
    return model.history.filter(id=pk).order_by('-history_date', '-history_id').first()


def _column_names(column) -> tuple[str, str]:
    """(group name, column name), also for a column deleted since, from its last history record."""
    if not isinstance(column, DeletedObject):
        return column.group.name, column.name
    record = _last_version(Column, column.pk)
    group = Group.objects.filter(pk=record.group_id).first() or _last_version(Group, record.group_id)
    return group.name, record.name


def _change_line(field: str, old, new) -> str:
    # simple_history hands an empty foreign key over as a DeletedObject without a pk.
    old, new = (None if isinstance(value, DeletedObject) and value.pk is None else value for value in (old, new))
    if field == 'title':
        return _('renamed the ticket from "%(old)s" to "%(new)s"') % {'old': old, 'new': new}
    if field == 'description':
        return _('edited the description')
    if field == 'column':
        (old_group, old_name), (new_group, new_name) = _column_names(old), _column_names(new)
        if old_group != new_group:
            return _('moved it from %(old)s to %(new)s') % {
                'old': f'{old_group} / {old_name}',
                'new': f'{new_group} / {new_name}',
            }
        return _('moved it from %(old)s to %(new)s') % {'old': old_name, 'new': new_name}
    if field == 'assignee':
        if not old:
            return _('assigned it to %(person)s') % {'person': _person(new)}
        if not new:
            return _('removed %(person)s as assignee') % {'person': _person(old)}
        return _('changed the assignee from %(old)s to %(new)s') % {'old': _person(old), 'new': _person(new)}
    if field == 'size':
        return _('set the size to %(size)s') % {'size': Ticket.Size(new).label} if new else _('cleared the size')
    if field == 'labels':
        # With foreign_keys_are_objs each through row holds the Label itself (or a DeletedObject).
        old_names = {str(row['label']) for row in old}
        new_names = {str(row['label']) for row in new}
        parts = [_('added label "%(name)s"') % {'name': name} for name in sorted(new_names - old_names)]
        parts += [_('removed label "%(name)s"') % {'name': name} for name in sorted(old_names - new_names)]
        return ', '.join(parts)
    return _('changed %(field)s') % {'field': field}


def _relation_line(record, ticket: Ticket) -> str:
    if record.source_id == ticket.pk:
        relation = f'{Relation.Type(record.type).label} {Ticket(pk=record.target_id).key}'
    else:
        relation = f'{Relation.INVERSE_LABELS[record.type]} {Ticket(pk=record.source_id).key}'
    if record.history_type == '+':
        return _('added "%(relation)s"') % {'relation': relation}
    return _('removed "%(relation)s"') % {'relation': relation}


def build_feed(ticket: Ticket) -> list[Entry]:
    entries = []
    previous = None
    for record in ticket.history.select_related('history_user').order_by('history_date', 'history_id'):
        if previous is None:
            entries.append(
                Entry(
                    record.history_date,
                    record.history_user,
                    [_('created the ticket')],
                    icon='bi-plus-circle',
                    via=_via(record),
                ),
            )
        else:
            delta = record.diff_against(previous, excluded_fields=QUIET_FIELDS, foreign_keys_are_objs=True)
            changes = [change for change in delta.changes if _change_line(change.field, change.old, change.new)]
            if changes:
                entries.append(
                    Entry(
                        record.history_date,
                        record.history_user,
                        [_change_line(change.field, change.old, change.new) for change in changes],
                        fallback=record.history_change_reason or _('Someone'),
                        icon=FIELD_ICONS.get(changes[0].field, 'bi-dot'),
                        via=_via(record),
                    ),
                )
        previous = record

    relation_records = Relation.history.filter(Q(source_id=ticket.pk) | Q(target_id=ticket.pk)).exclude(
        history_type='~',
    )
    entries += [
        Entry(
            record.history_date,
            record.history_user,
            [_relation_line(record, ticket)],
            fallback=record.history_change_reason or _('Someone'),
            icon='bi-link-45deg',
            via=_via(record),
        )
        for record in relation_records.select_related('history_user')
    ]

    comments = (
        ticket.comments.filter(parent=None)
        .select_related('author')
        .prefetch_related(
            Prefetch(
                'replies',
                queryset=Comment.objects.select_related('author').order_by('-created_at', '-id'),
            ),
        )
    )
    created = Comment.history.filter(ticket_id=ticket.pk, history_type='+').only('id', 'history_change_reason')
    via = {record.id: _via(record) for record in created}
    # A comment is only ever changed by its author editing it.
    edited = set(Comment.history.filter(ticket_id=ticket.pk, history_type='~').values_list('id', flat=True))
    for comment in comments:
        comment.via, comment.edited = via.get(comment.pk, ''), comment.pk in edited
        for reply in comment.replies.all():
            reply.via, reply.edited = via.get(reply.pk, ''), reply.pk in edited
        entries.append(Entry(comment.created_at, comment.author, comment=comment))
    # Newest first; replies under a comment are ordered the same way.
    return sorted(entries, key=lambda entry: entry.when, reverse=True)
