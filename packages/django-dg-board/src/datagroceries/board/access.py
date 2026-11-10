"""What someone may do on the board, per group: the one place every page, form, API call and MCP tool
asks, so an agent never does more than its person may.

It asks the project's `People` (datagroceries.core.people.may), after `may_use`: by default whoever may
use the board may do everything. A ticket's rights are those of its group. Who may not read a group does
not see its tickets: they are missing from boards, searches and the API, a page of one is not found, and
a relation to one shows as a ticket they cannot see. Someone not signed in sees nothing of the board,
whatever the project's `may_use` says, also where a wiki page names a ticket.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from datagroceries.board.conf import SCOPE
from datagroceries.board.models import KEY_RE, Group, Ticket
from datagroceries.core import people

READ, COMMENT, WRITE, MANAGE = people.RIGHTS


def _uses(user) -> bool:
    return user is not None and user.is_authenticated and people.may_use(user, SCOPE)


def may(user, right: str, group: Group | None) -> bool:
    """Whether `user` has `right` in `group`, or with None, outside any group, such as to make one."""
    return _uses(user) and people.may(user, right, group)


def visible_to(group: Group):
    """Whether a person may read `group`'s tickets, as a function of them: for a ticket's text to mute the
    @-mentions of people who cannot see it (datagroceries.core.mentions)."""
    return lambda user: may(user, READ, group)


def groups(user, right: str = READ) -> list[Group]:
    """The groups in which `user` has `right`, in the board's order; none for no user, as outside a request."""
    if not _uses(user):
        return []
    return [group for group in Group.objects.all() if people.may(user, right, group)]


def tickets(user, queryset=None):
    """The tickets of `queryset`, by default all, that `user` may read."""
    queryset = Ticket.objects.all() if queryset is None else queryset
    return queryset.filter(column__group__in=groups(user, READ))


def ticket(user, key_or_pk, queryset=None) -> Ticket:
    """The ticket with this key or primary key that `user` may read; not found otherwise, whether it
    exists or not."""
    if isinstance(key_or_pk, str):
        match = KEY_RE.match(key_or_pk.strip().upper())
        if not match:
            raise Http404(f'No ticket {key_or_pk}.')
        key_or_pk = int(match[1])
    found = tickets(user, queryset).filter(pk=key_or_pk).first()
    if found is None:
        raise Http404(f'No ticket {key_or_pk}.')
    return found


def require(user, right: str, group: Group | None):
    if not may(user, right, group):
        raise PermissionDenied


def rights(user, group: Group | None) -> dict[str, bool]:
    """What `user` may do in `group`, by right, for a template: `can.write`."""
    return {right: may(user, right, group) for right in people.RIGHTS}


def mark_hidden(user, others):
    """Mark the tickets among `others` that `user` may not read, as `hidden`, so a page shows them as a
    ticket they cannot see rather than by name."""
    readable = {group.pk for group in groups(user, READ)}
    for other in others:
        other.hidden = other.column.group_id not in readable
    return others


def readers(group: Group, users) -> list:
    """Those of `users` who may read `group`: whom a ticket in it may be assigned to, and who hear about it."""
    return [user for user in users if user is not None and may(user, READ, group)]
