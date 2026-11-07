"""What the ticket pages and the API both do to tickets, so both follow the same rules and tell the
same people. Validation stays with the callers: the pages' forms, and the API's serializers."""

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from datagroceries.board import notifications
from datagroceries.board.models import Attachment, Column, Comment, Group, Label, Relation, Ticket


def link_attachments(ticket: Ticket, text: str):
    """Attach the images uploaded while writing `text` before the ticket existed."""
    prefix = reverse('dg_board:attachment', args=[0]).removesuffix('0/')
    ids = [int(pk) for pk in re.findall(rf'{re.escape(prefix)}(\d+)/', text)]
    Attachment.objects.filter(pk__in=ids, ticket=None).update(ticket=ticket)


def create(request, column: Column, title: str, *, before: Ticket | None = None, labels=(), **fields) -> Ticket:
    """A new ticket by the requesting user in `column`, just above `before` or at the column's bottom.

    `fields` are other Ticket fields: description, assignee, size.
    """
    with transaction.atomic():
        ticket = Ticket(title=title, creator=request.user, **fields)
        ticket.move_to(column, before=before, after=None if before else column.tickets.last())
        if labels:
            set_labels(ticket, labels)
        link_attachments(ticket, ticket.description)
        notifications.ticket_created(request, ticket)
    return ticket


def add_child(request, parent: Ticket, title: str) -> Ticket:
    """A new ticket as a child of `parent`, at the bottom of its group's intake column."""
    with transaction.atomic():
        child = create(request, parent.column.group.intake_column(), title)
        Relation.objects.create(source=parent, target=child, type=Relation.Type.PARENT_OF)
    return child


def set_text(request, ticket: Ticket, field: str, value: str):
    """Set the title or the description; people newly @-mentioned in a description hear about it."""
    before = getattr(ticket, field)
    setattr(ticket, field, value)
    ticket.save()
    link_attachments(ticket, ticket.description)
    if field == 'description':
        notifications.text_written(request, ticket, before, value)


def move(request, ticket: Ticket, column: Column, *, before: Ticket | None = None, after: Ticket | None = None):
    """Put the ticket in `column`, of any group, just above `before`, just below `after` or else at the
    column's top; its watchers hear when it becomes done."""
    was_done = ticket.column.category == Column.Category.DONE
    if before is None and after is None:
        before = column.tickets.exclude(pk=ticket.pk).first()
    ticket.move_to(column, before=before, after=after)
    notifications.moved(request, ticket, was_done=was_done)


def move_to_group(request, ticket: Ticket, group: Group):
    """Move the ticket to the top of the matching column of `group`."""
    if group == ticket.column.group:
        return
    column = group.matching_column(ticket.column)
    if column is None:
        raise ValidationError(f'{group} has no columns yet.')
    move(request, ticket, column)


def assign(request, ticket: Ticket, user):
    """Assign the ticket to `user`, or to nobody; a new assignee hears about it and starts watching."""
    before = ticket.assignee_id
    ticket.assignee = user
    ticket.save()
    if user is not None and user.pk != before:
        notifications.assigned(request, ticket)


def set_labels(ticket: Ticket, names):
    """Replace the ticket's labels, making the ones that do not exist yet."""
    ticket.labels.set([Label.objects.get_or_create(name=name)[0] for name in sorted(set(names))])


def add_comment(request, form) -> Comment:
    """Save a valid CommentForm; the people it mentions and the ticket's watchers hear about it."""
    comment = form.save()
    link_attachments(comment.ticket, comment.body)
    notifications.commented(request, comment)
    return comment


def edit_comment(request, comment: Comment, body: str):
    """Change a comment's text. Only the people it newly @-mentions hear about it: the watchers had the
    first version, and the comment now shows as edited."""
    before = comment.body
    comment.body = body
    comment.save()
    link_attachments(comment.ticket, body)
    notifications.text_written(request, comment.ticket, before, body, f'#comment-{comment.pk}')


def toggle_blocked(request, ticket: Ticket, reason: str):
    """Block an unblocked ticket or unblock a blocked one, with a comment that says why."""
    with transaction.atomic():
        ticket.is_blocked = not ticket.is_blocked
        ticket.save()
        Comment.objects.create(ticket=ticket, author=request.user, body=reason, sets_blocked=ticket.is_blocked)
        notifications.blocked(request, ticket, reason)
