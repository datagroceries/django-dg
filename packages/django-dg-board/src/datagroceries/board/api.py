"""The board's REST API: read and change tickets as the person whose token it is, or through the
board's MCP tools (datagroceries.board.mcp), which run these views.

Changes go through datagroceries.board.operations, like the pages, so the rules and the notifications are the
same, and relations, comments and blocking are validated by the pages' own forms. The history names the
token: "via Claude Code on my laptop".
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from datagroceries.board import access, notifications, operations
from datagroceries.board.access import COMMENT, WRITE
from datagroceries.board.conf import SCOPE
from datagroceries.board.forms import BlockForm, CommentForm, RelationForm
from datagroceries.board.models import KEY_RE, Column, Comment, Group, Relation, Ticket
from datagroceries.core import backlinks, people
from datagroceries.core.api import form_errors, person, validated
from datagroceries.core.authentication import DataGroceriesAuthentication, HasTokenScope

LIST_LIMIT = 50
MAX_LIST_LIMIT = 200
# How a relation reads from each side, in the words RelationForm takes: {(type, seen from the target): kind}.
# "Relates to" reads the same from both sides.
RELATION_KINDS = {value: kind for kind, value in RelationForm.KINDS.items()} | {
    (Relation.Type.RELATES_TO, True): 'relates_to',
}


class TicketFieldsSerializer(serializers.Serializer):
    """The fields a ticket is created or changed with; only the ones sent are applied."""

    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, trim_whitespace=False)
    group = serializers.SlugField(help_text="A group's slug.")
    column = serializers.CharField(help_text="A column's id, or its name within the group.")
    assignee = serializers.CharField(allow_null=True)
    size = serializers.ChoiceField(choices=['', *Ticket.Size.values], allow_null=True)
    labels = serializers.ListField(child=serializers.CharField(max_length=50))


class TicketCreateSerializer(TicketFieldsSerializer):
    parent = serializers.CharField(required=False, help_text="The parent's key.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = name == 'title'


class BlockSerializer(serializers.Serializer):
    blocked = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True, default='')


class RelationSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=list(RelationForm.KINDS))
    ticket = serializers.CharField(help_text="The other ticket's key.")


class CommentSerializer(serializers.Serializer):
    body = serializers.CharField()
    parent = serializers.IntegerField(required=False, help_text='The id of the comment this replies to.')


class CommentEditSerializer(serializers.Serializer):
    # Blank is allowed here, for a comment that blocked or unblocked the ticket; the view decides.
    body = serializers.CharField(allow_blank=True, help_text='The whole new text, Markdown.')


def _find(request, key: str, queryset=None) -> Ticket:
    """The ticket with this key, if the requesting user may read it; not found otherwise."""
    queryset = access.tickets(request.user, queryset)
    match = KEY_RE.match(key.upper())
    ticket = queryset.filter(pk=int(match[1])).first() if match else None
    if ticket is None:
        raise NotFound(f'No ticket {key}.')
    return ticket


def _named(value: str):
    """The person on the board whom a handle (with or without its @) or an email address names, or None."""
    value = value.strip().removeprefix('@').lower()
    if '@' in value:
        return next((user for user in people.members(SCOPE) if (people.email(user) or '').lower() == value), None)
    return people.by_handle(SCOPE).get(value)


def _member(value: str | None, group: Group):
    """The person `value` names, to assign a ticket in `group` to."""
    if value is None:
        return None
    user = _named(value)
    if user is None:
        raise ValidationError({'assignee': [f'Nobody on the board has the handle or email address {value}.']})
    if not access.readers(group, [user]):
        raise ValidationError({'assignee': [f'{value} may not see {group}.']})
    return user


def _require(request, right: str, group: Group):
    if not access.may(request.user, right, group):
        raise PermissionDenied(f'You may not {right} in {group}.')


def _column(group: Group | None, column: str | None, current_group: Group | None = None) -> Column | None:
    """The column that `group` and `column` name; a column's name is looked up in `group`, or else in
    `current_group`. Without a column, the group's intake column; None when neither is given."""
    if group is None and column is None:
        return None
    if column is None:
        found = group.intake_column()
        if found is None:
            raise ValidationError({'group': [f'{group} has no columns yet.']})
        return found
    within = group or current_group
    columns = Column.objects.select_related('group')
    if column.isdigit():
        found = columns.filter(pk=int(column)).first()
    else:
        found = columns.filter(group=within, name__iexact=column).first() if within else None
    if found is None or (within is not None and found.group_id != within.pk):
        where = f' in {within}' if within else ''
        raise ValidationError({'column': [f'No column {column!r}{where}.']})
    return found


def _group(request, slug: str | None) -> Group | None:
    """The group with this slug, if the requesting user may read it."""
    if slug is None:
        return None
    group = next((group for group in access.groups(request.user) if group.slug == slug), None)
    if group is None:
        raise ValidationError({'group': [f'No group {slug!r}.']})
    return group


def _summary(request, ticket: Ticket) -> dict:
    return {
        'key': ticket.key,
        'title': ticket.title,
        'url': request.build_absolute_uri(ticket.get_absolute_url()),
        'group': ticket.column.group.slug,
        'column': ticket.column.name,
        'category': ticket.column.category,
        'assignee': person(ticket.assignee),
        'size': ticket.size,
        'labels': [label.name for label in ticket.labels.all()],
        'is_blocked': ticket.is_blocked,
        'created_at': ticket.created_at,
        'closed_at': ticket.closed_at,
    }


def _comment(comment: Comment) -> dict:
    kind = {True: 'blocked', False: 'unblocked', None: 'comment'}[comment.sets_blocked]
    return {
        'id': comment.pk,
        'kind': kind,
        'author': person(comment.author),
        'created_at': comment.created_at,
        'body': comment.body,
    }


def _related(other: Ticket) -> dict:
    """Another ticket, as a relation names it: by key and title, unless its reader may not read it."""
    if other.hidden:
        return {'key': None, 'title': 'A ticket you cannot see', 'category': other.column.category}
    return {'key': other.key, 'title': other.title, 'category': other.column.category}


def _detail(request, ticket: Ticket) -> dict:
    relations = [
        (RELATION_KINDS[relation.type, False], relation.target) for relation in ticket.outgoing_relations.all()
    ] + [(RELATION_KINDS[relation.type, True], relation.source) for relation in ticket.incoming_relations.all()]
    access.mark_hidden(request.user, [other for _, other in relations])
    blockers = access.mark_hidden(request.user, list(ticket.open_blockers().select_related('column')))
    comments = ticket.comments.filter(parent=None).select_related('author').prefetch_related('replies__author')
    return {
        **_summary(request, ticket),
        'description': ticket.description,
        'creator': person(ticket.creator),
        'open_blockers': [None if blocker.hidden else blocker.key for blocker in blockers],
        'relations': [
            {'kind': kind, **_related(other)}
            for kind, other in sorted(relations, key=lambda relation: (relation[0], relation[1].pk))
        ],
        'comments': [
            {**_comment(comment), 'replies': [_comment(reply) for reply in comment.replies.all()]}
            for comment in comments
        ],
        'watchers': [person(watcher.user) for watcher in ticket.watchers.select_related('user')],
        'attachments': [
            {'name': attachment.name, 'url': request.build_absolute_uri(attachment.get_absolute_url())}
            for attachment in ticket.attachments.all()
        ],
        'code': [
            {
                'kind': reference.kind,
                'ref': reference.ref,
                'title': reference.title,
                'author': reference.author,
                'state': reference.state,
                'happened_at': reference.happened_at,
                'url': reference.url,
            }
            for reference in ticket.code_references.all()
        ],
        # What names the ticket in the other DataGroceries apps, such as wiki pages.
        'named_in': [
            {'kind': str(source.label), 'title': place.title, 'url': request.build_absolute_uri(place.url)}
            for source, places in backlinks.find(request, ticket.key)
            for place in places
        ],
    }


def _detail_of(request, ticket: Ticket) -> dict:
    """The ticket as it is now in the database, with everything _detail shows loaded in a few queries."""
    return _detail(
        request,
        Ticket.objects.select_related('column__group', 'creator', 'assignee')
        .prefetch_related(
            'labels',
            'outgoing_relations__target__column',
            'incoming_relations__source__column',
            'attachments',
            'code_references',
        )
        .get(pk=ticket.pk),
    )


class TicketApiView(DataGroceriesAuthentication, APIView):
    # The board's area (datagroceries.board.mcp.AREA) keeps it to the members (datagroceries.core.people).
    permission_classes = (HasTokenScope,)
    token_scope = 'board'  # noqa: S105 - an area's name, not a secret


class TicketGroupsView(TicketApiView):
    def get(self, request):
        return Response(
            [
                {
                    'slug': group.slug,
                    'name': group.name,
                    'columns': [
                        {'id': column.pk, 'name': column.name, 'category': column.category}
                        for column in group.columns.all()
                    ],
                }
                for group in access.groups(request.user)
            ],
        )


class TicketListCreateView(TicketApiView):
    def get(self, request):
        """Tickets matching every filter given: a search's best matches first, else newest first."""
        tickets = access.tickets(
            request.user, Ticket.objects.select_related('column__group', 'assignee').prefetch_related('labels')
        )
        params = request.query_params
        if query := params.get('q', '').strip():
            tickets = tickets.search(query)
        if slug := params.get('group'):
            tickets = tickets.filter(column__group=_group(request, slug))
        if categories := params.getlist('category'):
            tickets = tickets.filter(column__category__in=categories)
        if assignees := params.getlist('assignee'):
            found = [request.user if value == 'me' else _named(value) for value in assignees if value != 'none']
            matches = Q(assignee__in=[user for user in found if user])
            if 'none' in assignees:
                matches |= Q(assignee=None)
            tickets = tickets.filter(matches)
        if labels := params.getlist('label'):
            tickets = tickets.filter(pk__in=Ticket.objects.filter(labels__name__in=labels).values('pk'))
        if params.get('blocked') in ('true', 'false'):
            tickets = tickets.filter(is_blocked=params['blocked'] == 'true')
        limit = min(int(params.get('limit', LIST_LIMIT)), MAX_LIST_LIMIT)
        # A search ranks its best matches first; a plain list is newest first.
        ordered = tickets if query else tickets.order_by('-pk')
        return Response(
            {'count': tickets.count(), 'results': [_summary(request, ticket) for ticket in ordered[:limit]]}
        )

    def post(self, request):
        data = validated(TicketCreateSerializer, request)
        with transaction.atomic():
            column = _column(_group(request, data.get('group')), data.get('column'))
            if column is None:
                raise ValidationError({'group': ['Give a group, a column or both.']})
            _require(request, WRITE, column.group)
            parent = _find(request, data['parent']) if 'parent' in data else None
            if parent is not None:
                _require(request, WRITE, parent.column.group)
            ticket = operations.create(
                request,
                column,
                data['title'],
                labels=data.get('labels', ()),
                description=data.get('description', ''),
                assignee=_member(data.get('assignee'), column.group),
                size=data.get('size') or '',
            )
            if parent is not None:
                Relation.objects.create(source=parent, target=ticket, type=Relation.Type.PARENT_OF)
        return Response(_detail_of(request, ticket), status=status.HTTP_201_CREATED)


class TicketDetailView(TicketApiView):
    def get(self, request, key):
        return Response(_detail_of(request, _find(request, key)))

    def patch(self, request, key):
        data = validated(TicketFieldsSerializer, request, partial=True)
        with transaction.atomic():
            ticket = _find(request, key, Ticket.objects.select_for_update().select_related('column__group'))
            _require(request, WRITE, ticket.column.group)
            group = _group(request, data.get('group'))
            if group is not None:
                _require(request, WRITE, group)
                try:
                    operations.move_to_group(request, ticket, group)
                except DjangoValidationError as error:
                    raise ValidationError({'group': error.messages}) from error
            if 'column' in data:
                column = _column(None, data['column'], ticket.column.group)
                if column != ticket.column:
                    operations.move(request, ticket, column)
            if 'assignee' in data:
                operations.assign(request, ticket, _member(data['assignee'], ticket.column.group))
            if 'size' in data:
                ticket.size = data['size'] or ''
                ticket.save()
            if 'labels' in data:
                operations.set_labels(ticket, data['labels'])
            for field in ('title', 'description'):
                if field in data and data[field] != getattr(ticket, field):
                    operations.set_text(request, ticket, field, data[field])
        return Response(_detail_of(request, ticket))


class TicketCommentsView(TicketApiView):
    def post(self, request, key):
        data = validated(CommentSerializer, request)
        ticket = _find(request, key)
        _require(request, COMMENT, ticket.column.group)
        form = CommentForm(
            {'body': data['body'], 'parent': data.get('parent')},
            instance=Comment(ticket=ticket, author=request.user),
        )
        if not form.is_valid():
            raise form_errors(form)
        return Response(_comment(operations.add_comment(request, form)), status=status.HTTP_201_CREATED)


class TicketCommentView(TicketApiView):
    def patch(self, request, key, comment_id):
        """Change the text of a comment or reply, as its author does on the ticket page: only the
        people it newly @-mentions hear about it."""
        ticket = _find(request, key)
        _require(request, COMMENT, ticket.column.group)
        comment = ticket.comments.filter(pk=comment_id).first()
        if comment is None:
            raise NotFound(f'No comment {comment_id} on {ticket.key}.')
        if comment.author_id != request.user.pk:
            raise PermissionDenied('Only its author can edit a comment.')
        body = validated(CommentEditSerializer, request)['body'].strip()
        # A comment that blocked or unblocked the ticket may go without a reason, as when it was made.
        if not body and comment.sets_blocked is None:
            raise ValidationError({'body': ['A comment needs text.']})
        operations.edit_comment(request, comment, body)
        return Response(_comment(comment))


class TicketRelationsView(TicketApiView):
    def post(self, request, key):
        data = validated(RelationSerializer, request)
        ticket = _find(request, key)
        _require(request, WRITE, ticket.column.group)
        form = RelationForm({'kind': data['kind'], 'other': data['ticket']}, ticket=ticket, user=request.user)
        if not form.is_valid():
            raise form_errors(form)
        form.relation.save()
        return Response(_detail_of(request, ticket), status=status.HTTP_201_CREATED)

    def delete(self, request, key):
        data = validated(RelationSerializer, request)
        ticket, other = _find(request, key), _find(request, data['ticket'])
        _require(request, WRITE, ticket.column.group)
        relation_type, reversed_ = RelationForm.KINDS[data['kind']]
        source, target = (other, ticket) if reversed_ else (ticket, other)
        matches = Q(source=source, target=target)
        if relation_type == Relation.Type.RELATES_TO:
            # "Relates to" reads the same both ways, so it may be stored either way round.
            matches |= Q(source=target, target=source)
        relations = list(Relation.objects.filter(matches, type=relation_type))
        if not relations:
            raise ValidationError({'detail': [f'{ticket.key} has no "{data["kind"]}" relation to {other.key}.']})
        # One by one, so each removal gets its history record.
        for relation in relations:
            relation.delete()
        return Response(_detail_of(request, ticket))


class TicketBlockView(TicketApiView):
    def post(self, request, key):
        data = validated(BlockSerializer, request)
        with transaction.atomic():
            ticket = _find(request, key, Ticket.objects.select_for_update().select_related('column__group'))
            _require(request, WRITE, ticket.column.group)
            if data['blocked'] == ticket.is_blocked:
                state = 'blocked' if ticket.is_blocked else 'not blocked'
                raise ValidationError({'blocked': [f'{ticket.key} is already {state}.']})
            form = BlockForm({'reason': data['reason']}, ticket=ticket)
            if not form.is_valid():
                raise form_errors(form)
            operations.toggle_blocked(request, ticket, form.cleaned_data['reason'])
        return Response(_detail_of(request, ticket))


class TicketWatchView(TicketApiView):
    def post(self, request, key):
        """Start watching the ticket."""
        ticket = _find(request, key)
        notifications.watch(ticket, request.user)
        return Response(_detail_of(request, ticket))

    def delete(self, request, key):
        """Stop watching the ticket."""
        ticket = _find(request, key)
        ticket.watchers.filter(user=request.user).delete()
        return Response(_detail_of(request, ticket))
