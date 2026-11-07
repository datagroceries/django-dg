"""Messages about tickets, to the people watching them, through datagroceries.core.notifications.

The views call these after a change; nothing here listens to model signals, so bulk changes notify
nobody. Nobody is told about their own change, and a message goes out only
once the change is committed.

Each person reads a message in their own language (datagroceries.core.people.language), whatever language the
page or the API that made the change was in, so a message is a sentence still to translate.
"""

from django.utils.translation import gettext_lazy as _

from datagroceries.board.conf import SCOPE
from datagroceries.board.models import Column, Ticket, Watcher
from datagroceries.core import mentions, notifications, people
from datagroceries.core.notifications import Message


def mentioned_users(text: str) -> list:
    """The people @-mentioned in `text`."""
    return mentions.mentioned(SCOPE, text)


def watch(ticket: Ticket, *users):
    for user in users:
        if user is not None:
            Watcher.objects.get_or_create(ticket=ticket, user=user)


def _url(request, ticket: Ticket, anchor: str = '') -> str:
    """The address of the ticket's page, or with `anchor` ("#comment-12") of a place on it."""
    return request.build_absolute_uri(f'{ticket.get_absolute_url()}{anchor}')


def _watchers(ticket: Ticket, *excluded) -> list:
    excluded_ids = {user.pk for user in excluded if user is not None}
    return [watcher.user for watcher in ticket.watchers.select_related('user') if watcher.user_id not in excluded_ids]


def ticket_created(request, ticket: Ticket):
    watch(ticket, ticket.creator)
    if ticket.assignee:
        assigned(request, ticket)
    text_written(request, ticket, '', ticket.description)


def assigned(request, ticket: Ticket):
    """Tell the new assignee, who also starts watching."""
    watch(ticket, ticket.assignee)
    summary = notifications.say(
        _('%(person)s assigned %(ticket)s to you'), person=people.name(request.user), ticket=ticket
    )
    message = Message('assigned', summary, _url(request, ticket), about=ticket, actor=request.user)
    notifications.send([ticket.assignee], message)


def text_written(request, ticket: Ticket, before: str, after: str, anchor: str = ''):
    """Tell the people @-mentioned in `after` and not already in `before`, who also start watching;
    their link goes to `anchor` on the ticket's page, when given."""
    before_ids = {user.pk for user in mentioned_users(before)}
    new = [user for user in mentioned_users(after) if user.pk not in before_ids]
    watch(ticket, *new)
    summary = notifications.say(
        _('%(person)s mentioned you in %(ticket)s'), person=people.name(request.user), ticket=ticket
    )
    notifications.send(new, Message('mentioned', summary, _url(request, ticket, anchor), ticket, request.user))


def commented(request, comment):
    """Tell the people @-mentioned in the comment, and everyone else watching the ticket."""
    ticket, author = comment.ticket, comment.author
    watch(ticket, author)
    mentioned = mentioned_users(comment.body)
    watch(ticket, *mentioned)
    # Straight to the comment, not the top of a long ticket.
    url = _url(request, ticket, f'#comment-{comment.pk}')
    names = {'person': people.name(author), 'ticket': ticket}
    about = {'about': ticket, 'actor': author, 'quote': notifications.snippet(comment.body)}
    summary = notifications.say(_('%(person)s mentioned you on %(ticket)s'), **names)
    notifications.send(mentioned, Message('mentioned', summary, url, **about))
    summary = notifications.say(_('%(person)s commented on %(ticket)s'), **names)
    notifications.send(_watchers(ticket, *mentioned), Message('commented', summary, url, **about))


def moved(request, ticket: Ticket, *, was_done: bool):
    """Tell the watchers when a ticket enters a done column."""
    if ticket.column.category == Column.Category.DONE and not was_done:
        summary = notifications.say(
            _('%(person)s moved %(ticket)s to %(column)s'),
            person=people.name(request.user),
            ticket=ticket,
            column=ticket.column,
        )
        notifications.send(_watchers(ticket), Message('done', summary, _url(request, ticket), ticket, request.user))


def blocked(request, ticket: Ticket, reason: str):
    if ticket.is_blocked:
        kind, sentence = 'blocked', _('%(person)s blocked %(ticket)s')
    else:
        kind, sentence = 'unblocked', _('%(person)s unblocked %(ticket)s')
    summary = notifications.say(sentence, person=people.name(request.user), ticket=ticket)
    message = Message(kind, summary, _url(request, ticket), ticket, request.user, notifications.snippet(reason))
    notifications.send(_watchers(ticket), message)
