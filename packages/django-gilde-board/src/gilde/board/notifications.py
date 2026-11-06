"""Messages about tickets, to the people watching them, through gilde.core.notifications.

The views call these after a change; nothing here listens to model signals, so bulk changes notify
nobody. Nobody is told about their own change, and a message goes out only
once the change is committed.

Messages are in the project's language (LANGUAGE_CODE), whatever language the page or the API that made
the change was in: Django keeps no language per person, so that is the one the people share.
"""

import functools
import re

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

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


def _in_project_language(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with translation.override(settings.LANGUAGE_CODE):
            return function(*args, **kwargs)

    return wrapper


def _watchers(ticket: Ticket, *excluded) -> list:
    excluded_ids = {user.pk for user in excluded if user is not None}
    return [watcher.user for watcher in ticket.watchers.select_related('user') if watcher.user_id not in excluded_ids]


@_in_project_language
def ticket_created(request, ticket: Ticket):
    watch(ticket, ticket.creator)
    if ticket.assignee:
        assigned(request, ticket)
    text_written(request, ticket, '', ticket.description)


@_in_project_language
def assigned(request, ticket: Ticket):
    """Tell the new assignee, who also starts watching."""
    watch(ticket, ticket.assignee)
    summary = _('%(person)s assigned %(ticket)s to you') % {'person': people.name(request.user), 'ticket': ticket}
    _send([ticket.assignee], request.user, summary, _url(request, ticket))


@_in_project_language
def text_written(request, ticket: Ticket, before: str, after: str, anchor: str = ''):
    """Tell the people @-mentioned in `after` and not already in `before`, who also start watching;
    their link goes to `anchor` on the ticket's page, when given."""
    before_ids = {user.pk for user in mentioned_users(before)}
    new = [user for user in mentioned_users(after) if user.pk not in before_ids]
    watch(ticket, *new)
    summary = _('%(person)s mentioned you in %(ticket)s') % {'person': people.name(request.user), 'ticket': ticket}
    _send(new, request.user, summary, _url(request, ticket, anchor))


@_in_project_language
def commented(request, comment):
    """Tell the people @-mentioned in the comment, and everyone else watching the ticket."""
    ticket, author = comment.ticket, comment.author
    watch(ticket, author)
    mentioned = mentioned_users(comment.body)
    watch(ticket, *mentioned)
    quote = _snippet(comment.body)
    # Straight to the comment, not the top of a long ticket.
    url = _url(request, ticket, f'#comment-{comment.pk}')
    names = {'person': people.name(author), 'ticket': ticket}
    _send(mentioned, author, _('%(person)s mentioned you on %(ticket)s') % names, url, quote)
    _send(_watchers(ticket, *mentioned), author, _('%(person)s commented on %(ticket)s') % names, url, quote)


@_in_project_language
def moved(request, ticket: Ticket, *, was_done: bool):
    """Tell the watchers when a ticket enters a done column."""
    if ticket.column.category == Column.Category.DONE and not was_done:
        summary = _('%(person)s moved %(ticket)s to %(column)s') % {
            'person': people.name(request.user),
            'ticket': ticket,
            'column': ticket.column,
        }
        _send(_watchers(ticket), request.user, summary, _url(request, ticket))


@_in_project_language
def blocked(request, ticket: Ticket, reason: str):
    names = {'person': people.name(request.user), 'ticket': ticket}
    if ticket.is_blocked:
        summary = _('%(person)s blocked %(ticket)s') % names
    else:
        summary = _('%(person)s unblocked %(ticket)s') % names
    _send(_watchers(ticket), request.user, summary, _url(request, ticket), _snippet(reason))
