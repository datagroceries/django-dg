"""The board's area for agents: its token scope, and its MCP tools, which run the views of its REST API
(gilde.board.api). Registered with gilde.core in BoardConfig.ready()."""

from django.utils.translation import gettext_lazy as _

from gilde.board.api import (
    TicketBlockView,
    TicketCommentsView,
    TicketCommentView,
    TicketDetailView,
    TicketGroupsView,
    TicketListCreateView,
    TicketRelationsView,
    TicketWatchView,
)
from gilde.board.conf import SCOPE
from gilde.board.forms import RelationForm
from gilde.board.models import Column, Ticket
from gilde.core.areas import Area
from gilde.core.mcp import Tool

KEY = {'type': 'string', 'description': 'The ticket key, e.g. T-123.'}
MENTION = '@-mentioning someone by their handle (@ann, as the people in a ticket list them) tells them about it.'
TICKET_FIELDS = {
    'title': {'type': 'string', 'maxLength': 255, 'description': 'Required on create.'},
    'description': {'type': 'string', 'description': f'Markdown; replaces the whole description. {MENTION}'},
    'group': {
        'type': 'string',
        'description': "A group's slug, from list_ticket_groups. Changing it moves the ticket to the column of "
        'the same name there, else of the same category.',
    },
    'column': {
        'type': 'string',
        'description': "A column's name within the ticket's group, or its id. On create without one, the "
        "group's intake column.",
    },
    'assignee': {
        'type': ['string', 'null'],
        'description': "A person's handle, as in an @-mention, or their email address; null for nobody. "
        'A new assignee hears about it.',
    },
    'size': {
        'type': ['string', 'null'],
        'enum': ['', *Ticket.Size.values, None],
        'description': '"unknown" when it cannot be told; empty or null when not estimated yet.',
    },
    'labels': {
        'type': 'array',
        'items': {'type': 'string'},
        'description': 'Replaces all labels; a new name makes a new label.',
    },
}
TOOLS = (
    Tool(
        'list_ticket_groups',
        'List board groups',
        "The board's groups (teams and projects), each with its columns in board order.",
        TicketGroupsView,
        'GET',
        {},
    ),
    Tool(
        'search_tickets',
        'Search tickets',
        'Tickets matching every filter given, as summaries; get_ticket has the rest. A search lists the '
        'ticket it is the key of first, then title matches, then description matches; without q, newest first. '
        "Searching on a key is the quick look at one ticket, as get_ticket's answer is long.",
        TicketListCreateView,
        'GET',
        {
            'q': {'type': 'string', 'description': 'A key (T-831, or 831), or words in the title or description.'},
            'group': {'type': 'string', 'description': "A group's slug."},
            'category': {
                'type': 'array',
                'items': {'enum': Column.Category.values},
                'description': "The column's category; a ticket matches any of those given.",
            },
            'assignee': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Handles or email addresses; "me" for the connected person, "none" for unassigned.',
            },
            'label': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Label names; a ticket matches any of those given.',
            },
            'blocked': {'type': 'boolean'},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200, 'default': 50},
        },
    ),
    Tool(
        'get_ticket',
        'Read a ticket',
        'One ticket in full: description, comments, relations, watchers, attachments and linked code. Read '
        'it before commenting, to see who will hear about the comment.',
        TicketDetailView,
        'GET',
        {'key': KEY},
        path=('key',),
    ),
    Tool(
        'create_ticket',
        'Create a ticket',
        "Create a ticket. Without a column it goes to the group's intake column; a parent makes it a child. "
        'Deleting tickets and uploading attachments are not possible here.',
        TicketListCreateView,
        'POST',
        {**TICKET_FIELDS, 'parent': {'type': 'string', 'description': "The parent ticket's key."}},
        required=('title',),
    ),
    Tool(
        'update_ticket',
        'Change a ticket',
        'Change the fields given, and only those: move it, assign it, retitle it, and so on.',
        TicketDetailView,
        'PATCH',
        {'key': KEY, **TICKET_FIELDS},
        path=('key',),
    ),
    Tool(
        'comment_on_ticket',
        'Comment on a ticket',
        "Add a comment, or a reply to one. The ticket's watchers and anyone @-mentioned hear about it at once.",
        TicketCommentsView,
        'POST',
        {
            'key': KEY,
            'body': {'type': 'string', 'description': f'Markdown. {MENTION}'},
            'parent': {
                'type': 'integer',
                'description': 'The id of the comment this replies to; replies go one level deep.',
            },
        },
        required=('body',),
        path=('key',),
    ),
    Tool(
        'edit_comment',
        'Edit a comment',
        "Replace the text of a comment or reply you wrote; nobody else's. The watchers are not told "
        'again, only the people it newly @-mentions, and the comment shows as edited.',
        TicketCommentView,
        'PATCH',
        {
            'key': KEY,
            'comment_id': {'type': 'integer', 'description': "The comment's id, as get_ticket shows it."},
            'body': {'type': 'string', 'description': f'The whole new text, Markdown. {MENTION}'},
        },
        required=('body',),
        path=('key', 'comment_id'),
    ),
    Tool(
        'relate_tickets',
        'Relate two tickets',
        'Relate the ticket to another, read from the ticket in `key`: "blocked_by" with `ticket` T-2 means '
        'T-2 blocks it. A ticket has at most one parent, and loops of parents or blockers are refused.',
        TicketRelationsView,
        'POST',
        {'key': KEY, 'kind': {'enum': list(RelationForm.KINDS)}, 'ticket': {**KEY, 'description': "The other's key."}},
        required=('kind', 'ticket'),
        path=('key',),
    ),
    Tool(
        'unrelate_tickets',
        'Remove a relation',
        'Remove a relation between the ticket and another, named as relate_tickets names it.',
        TicketRelationsView,
        'DELETE',
        {'key': KEY, 'kind': {'enum': list(RelationForm.KINDS)}, 'ticket': {**KEY, 'description': "The other's key."}},
        required=('kind', 'ticket'),
        path=('key',),
        destructive=True,
    ),
    Tool(
        'set_ticket_blocked',
        'Block or unblock a ticket',
        'Block a ticket, or unblock it, with a comment saying why; its watchers hear about it.',
        TicketBlockView,
        'POST',
        {
            'key': KEY,
            'blocked': {'type': 'boolean'},
            'reason': {
                'type': 'string',
                'description': 'Required to block, optional to unblock; it becomes a comment.',
            },
        },
        required=('blocked',),
        path=('key',),
    ),
    Tool(
        'watch_ticket',
        'Watch a ticket',
        'Start watching a ticket, so the connected person hears about its changes.',
        TicketWatchView,
        'POST',
        {'key': KEY},
        path=('key',),
    ),
    Tool(
        'unwatch_ticket',
        'Stop watching a ticket',
        'Stop watching a ticket.',
        TicketWatchView,
        'DELETE',
        {'key': KEY},
        path=('key',),
    ),
)
AREA = Area(
    scope=SCOPE,
    label=_('Board'),
    permission='gilde_board.use',
    instructions='The board is the ticket tracker: look a ticket up when someone mentions its key (T-123). '
    "A comment reaches the ticket's watchers at once.",
    tools=TOOLS,
)
