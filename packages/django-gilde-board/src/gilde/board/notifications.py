"""Messages about tickets, to the people watching them, through gilde.core.notifications.

The views call these after a change; nothing here listens to model signals, so bulk changes notify
nobody. Nobody is told about their own change, and a message goes out only
once the change is committed.
"""

import re

from gilde.board.conf import SCOPE
from gilde.board.models import Column, Ticket, Watcher
from gilde.core import notifications, people

# "@jasper" names the member whose handle is "jasper" (gilde.core.people).
MENTION_RE = re.compile(r'(?<![\w@.])@([a-z0-9][a-z0-9._-]*)', re.IGNORECASE)
SNIPPET_LENGTH = 300


def mentioned_users(text: str) -> list:
    """The people @-mentioned in `text`."""
    handles = {handle.lower().rstrip('.') for handle in MENTION_RE.findall(text or '')}
    return people.mentioned(SCOPE, handles) if handles else []


def watch(ticket: Ticket, *users):
    for user in users:
        if user is not None:
            Watcher.objects.get_or_create(ticket=ticket, user=user)


def _url(request, ticket: Ticket, anchor: str = '') -> str:
    """The address of the ticket's page, or with `anchor` ("#comment-12") of a place on it."""
    return request.build_absolute_uri(f'{ticket.get_absolute_url()}{anchor}')


def _snippet(text: str) -> str:
    text = text.strip()
    return text[:SNIPPET_LENGTH].rstrip() + '…' if len(text) > SNIPPET_LENGTH else text


def _send(users, actor, summary: str, url: str, quote: str = ''):
    notifications.notify([user for user in users if user.pk != actor.pk], summary, url, quote)


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
    _send(
        [ticket.assignee], request.user, f'{people.name(request.user)} assigned {ticket} to you', _url(request, ticket)
    )


def text_written(request, ticket: Ticket, before: str, after: str, anchor: str = ''):
    """Tell the people @-mentioned in `after` and not already in `before`, who also start watching;
    their link goes to `anchor` on the ticket's page, when given."""
    before_ids = {user.pk for user in mentioned_users(before)}
    new = [user for user in mentioned_users(after) if user.pk not in before_ids]
    watch(ticket, *new)
    _send(new, request.user, f'{people.name(request.user)} mentioned you in {ticket}', _url(request, ticket, anchor))


def commented(request, comment):
    """Tell the people @-mentioned in the comment, and everyone else watching the ticket."""
    ticket, author = comment.ticket, comment.author
    watch(ticket, author)
    mentioned = mentioned_users(comment.body)
    watch(ticket, *mentioned)
    quote = _snippet(comment.body)
    # Straight to the comment, not the top of a long ticket.
    url = _url(request, ticket, f'#comment-{comment.pk}')
    _send(mentioned, author, f'{people.name(author)} mentioned you on {ticket}', url, quote)
    _send(_watchers(ticket, *mentioned), author, f'{people.name(author)} commented on {ticket}', url, quote)


def moved(request, ticket: Ticket, *, was_done: bool):
    """Tell the watchers when a ticket enters a done column."""
    if ticket.column.category == Column.Category.DONE and not was_done:
        summary = f'{people.name(request.user)} moved {ticket} to {ticket.column}'
        _send(_watchers(ticket), request.user, summary, _url(request, ticket))


def blocked(request, ticket: Ticket, reason: str):
    what = 'blocked' if ticket.is_blocked else 'unblocked'
    summary = f'{people.name(request.user)} {what} {ticket}'
    _send(_watchers(ticket), request.user, summary, _url(request, ticket), _snippet(reason))
