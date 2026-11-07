import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gilde.board import github, notifications, operations
from gilde.board.activity import build_feed
from gilde.board.conf import SCOPE
from gilde.board.forms import (
    BlockForm,
    ChildForm,
    ColumnFormSet,
    CommentForm,
    DescriptionForm,
    GroupForm,
    RelationForm,
    TicketForm,
    TitleForm,
    fingerprint,
)
from gilde.board.models import KEY_RE, Attachment, CodeReference, Column, Comment, Group, Label, Relation, Ticket
from gilde.core import attachments, backlinks, people

board_required = people.may_use_required(SCOPE)

# Which tickets the board shows by their place among parents and children, as its Show filter names them.
BOARD_SHOW = {
    'all': gettext_lazy('All tickets'),
    'top': gettext_lazy('Top level'),
    'parents': gettext_lazy('Parents only'),
}
# Where the board remembers each viewer's last group and filters.
BOARD_SESSION_KEY = 'gilde_board'
CODE_KIND_ORDER = (CodeReference.Kind.PULL_REQUEST, CodeReference.Kind.BRANCH, CodeReference.Kind.COMMIT)
LANE_ORDER = ('column__group__position', 'column__position', 'rank', 'id')
# How many of the newest comments the quick view of a ticket shows; the ticket page has them all.
PEEK_COMMENTS = 3


def _drop_place(column: Column, before_id: int | None, moving: Ticket | None = None) -> dict:
    """Where a card dropped above ticket `before_id` goes: just above it, or below the column's last
    ticket when it is not in that column. As keyword arguments for `operations.move`.

    The board sends the ticket a card was dropped above rather than an index, because a filtered
    board shows only part of a column.
    """
    tickets = column.tickets.exclude(pk=moving.pk if moving else None)
    before = tickets.filter(pk=before_id).first()
    return {'before': before} if before else {'after': tickets.last()}


def _board_url(request, group: Group) -> str:
    """The way back from a ticket to its group's board: the viewer's remembered view of it, filters and
    all, or else the plain board of that group."""
    remembered = request.session.get(BOARD_SESSION_KEY, '')
    if parse_qs(remembered).get('group') == [group.slug]:
        return f'{reverse("gilde_board:board")}?{remembered}'
    return f'{reverse("gilde_board:board")}?group={group.slug}'


def _card_tickets():
    """Tickets with what their cards show beyond their own fields, in the board's order, leaving out
    those done longer ago than their group keeps them."""
    open_blocker = Relation.objects.filter(target=OuterRef('pk'), type=Relation.Type.BLOCKS).exclude(
        source__column__category=Column.Category.DONE,
    )
    latest_block_reason = Comment.objects.filter(ticket=OuterRef('pk'), sets_blocked=True).order_by('-created_at')
    # A ticket has at most one parent.
    parent_link = Relation.objects.filter(target=OuterRef('pk'), type=Relation.Type.PARENT_OF)
    comment_count = (
        Comment.objects.filter(ticket=OuterRef('pk')).order_by().values('ticket').annotate(n=Count('pk')).values('n')
    )
    return (
        Ticket.objects.on_board()
        .select_related('column__group', 'assignee')
        .prefetch_related('labels')
        .annotate(
            has_open_blocker=Exists(open_blocker),
            block_reason=Subquery(latest_block_reason.values('body')[:1]),
            comment_count=Coalesce(Subquery(comment_count), 0),
            parent_pk=Subquery(parent_link.values('source')[:1]),
            parent_title=Subquery(parent_link.values('source__title')[:1]),
        )
        .order_by(*LANE_ORDER)
    )


def _count_children(tickets: list[Ticket]):
    """Give each ticket its card's count of done children, and its parent's key."""
    children = Relation.objects.filter(type=Relation.Type.PARENT_OF, source__in=tickets).values_list(
        'source_id',
        'target__column__category',
    )
    progress = {}
    for parent_id, category in children:
        done, total = progress.get(parent_id, (0, 0))
        progress[parent_id] = (done + (category == Column.Category.DONE), total + 1)
    for ticket in tickets:
        ticket.children_done, ticket.children_total = progress.get(ticket.pk, (0, 0))
        ticket.parent_key = f'{settings.GILDE_BOARD_KEY_PREFIX}-{ticket.parent_pk}' if ticket.parent_pk else None


def _lanes(group: Group | None, tickets: list[Ticket]) -> list[dict]:
    """The lanes of a board of `tickets`: the columns of `group`, or across groups the column categories."""
    if group:
        return [
            {
                'column': column,
                'title': column.name,
                'category': column.category,
                'tickets': [t for t in tickets if t.column_id == column.pk],
            }
            for column in group.columns.all()
        ]
    # Across groups every group has its own columns, so the lanes are the column categories.
    return [
        {
            'column': None,
            'title': title,
            'category': category,
            'tickets': [t for t in tickets if t.column.category == category],
        }
        for category, title in Column.Category.choices
    ]


def _filtered(tickets, user, filters: dict):
    """The cards that pass the board's filters. Each filter takes several values and matches any of them."""
    assignees, creators, labels, show = filters['assignees'], filters['creators'], filters['labels'], filters['show']
    if assignees:
        ids = [user.pk if value == 'me' else int(value) for value in assignees if value != 'none']
        matches = Q(assignee_id__in=ids)
        if 'none' in assignees:
            matches |= Q(assignee=None)
        tickets = tickets.filter(matches)
    if creators:
        tickets = tickets.filter(creator_id__in=[user.pk if value == 'me' else int(value) for value in creators])
    if labels:
        matches = Q(pk__in=Ticket.objects.filter(labels__name__in=labels).values('pk'))
        if 'none' in labels:
            matches |= Q(pk__in=Ticket.objects.filter(labels=None).values('pk'))
        tickets = tickets.filter(matches)
    # Top level: no parent, so subtasks go. Parents only: tickets with subtasks. A ticket in between has both.
    parent_links = Relation.objects.filter(type=Relation.Type.PARENT_OF)
    if show == 'top':
        tickets = tickets.exclude(pk__in=parent_links.values('target'))
    elif show == 'parents':
        tickets = tickets.filter(pk__in=parent_links.values('source'))
    return tickets


def _family(parent) -> set[int]:
    """The ids of `parent` and everything under it, a level at a time. Relation.clean refuses loops, and
    the set difference would stop one anyway."""
    parent_links = Relation.objects.filter(type=Relation.Type.PARENT_OF)
    family = level = {parent.pk}
    while level:
        level = set(parent_links.filter(source__in=level).values_list('target', flat=True)) - family
        family = family | level
    return family


def _filter_people(group, assignees, creators):
    """Whom the assignee and creator filters offer: the people assigned to, or who created, a ticket on
    this board, whatever the other filters are; someone chosen already stays, so the choice can be taken
    off again."""
    on_board = Ticket.objects.on_board()
    if group:
        on_board = on_board.filter(column__group=group)
    chosen = [int(value) for value in assignees if value not in ('me', 'none')]
    chosen_creators = [int(value) for value in creators if value != 'me']
    members = people.members(SCOPE)
    return (
        members.filter(Q(pk__in=on_board.values('assignee')) | Q(pk__in=chosen)),
        members.filter(Q(pk__in=on_board.values('creator')) | Q(pk__in=chosen_creators)),
    )


# Never from the browser's cache: Back from a ticket that was just edited must show the edit.
@never_cache
@board_required
def board(request):
    # The board opens as its viewer left it: the group and filters they last chose, not the text search.
    if not request.GET and (remembered := request.session.get(BOARD_SESSION_KEY)):
        return redirect(f'{request.path}?{remembered}')
    groups = list(Group.objects.all())
    if not groups:
        return render(request, 'gilde_board/board.html', {'groups': groups})

    slug = request.GET.get('group')
    group = None if slug == 'all' else next((g for g in groups if g.slug == slug), None) if slug else groups[0]
    if slug and slug != 'all' and group is None:
        # A remembered group that has been deleted since.
        request.session.pop(BOARD_SESSION_KEY, None)
        return redirect(request.path)

    query = request.GET.get('q', '').strip()
    # A search sent with Enter (`open`) goes straight to the ticket its key names, done or not: its own, or
    # its number alone ("831"). Without it, as the board filters while the search is typed, the search only
    # filters: that URL, reloaded or come back to, shows the board again.
    opening = 'open' in request.GET
    if opening and (best := Ticket.objects.search(query).first()) and best.search_rank == 0:
        return redirect(best)
    # A search is a one-off, from the board or the Command Center: it leaves the remembered view alone.
    if not query:
        request.session[BOARD_SESSION_KEY] = urlencode(
            [(key, value) for key, values in request.GET.lists() if key not in ('q', 'open') for value in values],
        )

    tickets = _card_tickets()
    assignees, creators, labels = (request.GET.getlist(name) for name in ('assignee', 'creator', 'label'))
    show = request.GET.get('show', 'all')
    if show not in BOARD_SHOW:
        raise Http404(f'Unknown show {show!r}')
    filters = {'assignees': assignees, 'creators': creators, 'labels': labels, 'q': query, 'show': show}
    tickets = _filtered(tickets, request.user, filters)
    # One ticket and everything under it, subtasks of subtasks too, from Open on board on its page or the
    # subtask count on its card.
    parent = None
    if parent_key := request.GET.get('parent'):
        match = KEY_RE.match(parent_key)
        parent = Ticket.objects.filter(pk=int(match[1])).first() if match else None
        if parent is None:
            # A remembered parent that has been deleted since.
            request.session.pop(BOARD_SESSION_KEY, None)
            return redirect(request.path)
        tickets = tickets.filter(pk__in=_family(parent))
    if query:
        # The cards stay in their lanes' order, whatever the search ranks first.
        tickets = tickets.search(query).order_by(*LANE_ORDER)

    tickets = list(tickets.filter(column__group=group) if group else tickets)
    if opening and query and len(tickets) == 1:
        # One match for a word is as good as its key.
        return redirect(tickets[0])
    _count_children(tickets)

    users, creator_users = _filter_people(group, assignees, creators)
    other_filters = (
        [('assignee', v) for v in assignees]
        + [('creator', v) for v in creators]
        + [('label', v) for v in labels]
        + ([('show', show)] if show != 'all' else [])
        + ([('q', query)] if query else [])
    )

    return render(
        request,
        'gilde_board/board.html',
        {
            'groups': groups,
            'group': group,
            'lanes': _lanes(group, tickets),
            'users': users,
            'creator_users': creator_users,
            # Everyone a card can be assigned to, unlike the assignee filter's people with a ticket here.
            'assignable_users': people.members(SCOPE),
            'labels': Label.objects.all(),
            'filters': filters,
            'show_options': BOARD_SHOW.items(),
            'parent': parent,
            'is_filtered': bool(assignees or creators or labels or query or show != 'all' or parent),
            # The filters without the group, so switching group keeps them; and without the parent as well,
            # for the cross that takes it off.
            'filter_query': urlencode(other_filters + ([('parent', parent.key)] if parent else [])),
            'unparented_query': urlencode(other_filters),
        },
    )


@board_required
def ticket_search(request):
    """The tickets `q` finds, best first, for autocomplete fields."""
    tickets = Ticket.objects.search(request.GET.get('q', '')).select_related('column')[:20]
    return JsonResponse(
        {'results': [{'key': t.key, 'title': t.title, 'category': t.column.category} for t in tickets]},
    )


@board_required
@require_POST
def ticket_quick_create(request):
    """Create a ticket from a title typed into a board column, and return its card for the board."""
    column = get_object_or_404(Column.objects.select_related('group'), pk=int(request.POST['column']))
    title = request.POST.get('title', '').strip()[:255]
    if not title:
        return JsonResponse({'error': 'A ticket needs a title.'}, status=400)
    before = int(request.POST['before']) if request.POST.get('before') else None
    ticket = operations.create(request, column, title, before=column.tickets.filter(pk=before).first())
    # What the board's query annotates, for a ticket that has none of it yet.
    ticket.comment_count = ticket.children_done = ticket.children_total = 0
    ticket.has_open_blocker, ticket.block_reason = False, None
    card = render_to_string('gilde_board/_card.html', {'ticket': ticket, 'group': column.group}, request=request)
    return JsonResponse({'key': ticket.key, 'html': card})


@board_required
@require_POST
def ticket_move(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    column = get_object_or_404(Column, pk=int(request.POST['column']))
    before = int(request.POST['before']) if request.POST.get('before') else None
    operations.move(request, ticket, column, **_drop_place(column, before, moving=ticket))
    return JsonResponse({'key': ticket.key})


@board_required
@require_POST
def ticket_reorder(request, pk):
    """Move a ticket just above `before` or just below `after` in the order of all tickets, from a
    list of related tickets on a ticket page; its column stays."""
    ticket = get_object_or_404(Ticket, pk=pk)
    side = 'before' if request.POST.get('before') else 'after'
    neighbour = get_object_or_404(Ticket.objects.exclude(pk=pk), pk=int(request.POST[side]))
    ticket.move_to(ticket.column, **{side: neighbour})
    return JsonResponse({'key': ticket.key})


@board_required
def ticket_create(request):
    # The board's "+" above a card passes that card as `before`; its column is where the new one goes.
    before = int(request.GET['before']) if request.GET.get('before') else None
    column_id = get_object_or_404(Ticket, pk=before).column_id if before else request.GET.get('column')
    form = TicketForm(request.POST or None, initial={'column': column_id})
    if request.method == 'POST' and form.is_valid():
        data, column = form.cleaned_data, form.cleaned_data['column']
        ticket = operations.create(
            request,
            column,
            data['title'],
            before=column.tickets.filter(pk=before).first(),
            labels=data['labels_text'],
            description=data['description'],
            assignee=data['assignee'],
            size=data['size'],
        )
        return redirect(ticket)
    return render(request, 'gilde_board/ticket_form.html', {'form': form})


@board_required
@require_POST
def ticket_update(request, pk):
    """Save one property from the ticket page's sidebar, or the assignee from a card on the board; both post
    it as soon as it changes. A new assignee comes back as the card shows it."""
    field, values = request.POST['field'], request.POST.getlist('value')
    with transaction.atomic():
        ticket = get_object_or_404(Ticket.objects.select_for_update().select_related('column__group'), pk=pk)
        if field == 'column':
            column = get_object_or_404(Column, pk=int(values[0]), group=ticket.column.group)
            if column != ticket.column:
                operations.move(request, ticket, column)
        elif field == 'group':
            group = get_object_or_404(Group, pk=int(values[0]))
            try:
                operations.move_to_group(request, ticket, group)
            except ValidationError as error:
                return JsonResponse({'error': error.message}, status=400)
        elif field == 'assignee':
            assignee = get_object_or_404(people.members(SCOPE), pk=int(values[0])) if values[0] else None
            operations.assign(request, ticket, assignee)
            card = render_to_string('gilde_board/_card_assignee.html', {'ticket': ticket}, request=request)
            return JsonResponse({'key': ticket.key, 'card_assignee': card})
        elif field == 'size':
            if values[0] not in {'', *Ticket.Size.values}:
                return JsonResponse({'error': f'Unknown size {values[0]!r}.'}, status=400)
            ticket.size = values[0]
            ticket.save()
        elif field == 'labels':
            names = [name.strip() for value in values for name in value.split(',') if name.strip()]
            operations.set_labels(ticket, names)
        else:
            return JsonResponse({'error': f'{field!r} cannot be changed here.'}, status=400)
    return JsonResponse({'key': ticket.key})


def _act_on_text(request, ticket, forms):
    """Save a new title or description, unless someone else changed it since the page was loaded."""
    action = request.POST['action']
    form = forms[f'{action}_form'] = type(forms[f'{action}_form']).for_ticket(ticket, request.POST)
    if not form.is_valid():
        return None
    with transaction.atomic():
        stored = Ticket.objects.select_for_update().get(pk=ticket.pk)
        current = getattr(stored, action)
        if fingerprint(current) == form.cleaned_data['original']:
            operations.set_text(request, stored, action, form.cleaned_data[action])
            return redirect(stored)
        # The record that introduced the current text says who wrote it.
        writer = stored.history.filter(**{action: current}).earliest('history_date').history_user
        what = {'title': _('the title'), 'description': _('the description')}[action]
        form.add_error(
            None,
            _('%(who)s changed %(what)s while you were editing it. Copy your text, reload the page and apply it again.')
            % {'who': people.name(writer) if writer else _('Someone'), 'what': what},
        )
    return None


def _act_comment(request, ticket, forms):
    form = forms['comment_form'] = CommentForm(request.POST, instance=Comment(ticket=ticket, author=request.user))
    if not form.is_valid():
        return None
    comment = operations.add_comment(request, form)
    return redirect(f'{ticket.get_absolute_url()}#comment-{comment.pk}')


def _act_edit_comment(request, ticket, forms):
    # Only by its author. A comment that blocked or unblocked the ticket may be left without a reason.
    comment = get_object_or_404(ticket.comments, pk=request.POST['comment'], author=request.user)
    body = request.POST['body'].strip()
    if body or comment.sets_blocked is not None:
        operations.edit_comment(request, comment, body)
    else:
        messages.error(request, _('A comment needs text; the old one is kept.'))
    return redirect(f'{ticket.get_absolute_url()}#comment-{comment.pk}')


def _act_block(request, ticket, forms):
    form = forms['block_form'] = BlockForm(request.POST, ticket=ticket)
    if not form.is_valid():
        return None
    operations.toggle_blocked(request, ticket, form.cleaned_data['reason'])
    return redirect(ticket)


def _act_child(request, ticket, forms):
    form = forms['child_form'] = ChildForm(request.POST)
    if not form.is_valid():
        return None
    child = operations.add_child(request, ticket, form.cleaned_data['title'])
    messages.success(
        request, _('Created %(child)s as a child of %(ticket)s.') % {'child': child.key, 'ticket': ticket.key}
    )
    return redirect(ticket)


def _act_watch(request, ticket, forms):
    watching = ticket.watchers.filter(user=request.user)
    if watching.exists():
        watching.delete()
    else:
        notifications.watch(ticket, request.user)
    return redirect(ticket)


def _act_relation(request, ticket, forms):
    form = forms['relation_form'] = RelationForm(request.POST, ticket=ticket)
    if not form.is_valid():
        return None
    form.relation.save()
    return redirect(ticket)


def _act_unrelate(request, ticket, forms):
    relation = get_object_or_404(Relation, Q(source=ticket) | Q(target=ticket), pk=int(request.POST['relation']))
    relation.delete()
    return redirect(ticket)


def _act_delete(request, ticket, forms):
    # For a mistake or a duplicate; a ticket decided against goes to Won't do, and keeps its history.
    # Its comments, relations, watchers, code links and attachments go with it.
    board, key = _board_url(request, ticket.column.group), ticket.key
    files = [attachment.file for attachment in ticket.attachments.all()]
    with transaction.atomic():
        ticket.delete()
        # Only once the rows are gone for good.
        transaction.on_commit(lambda: [file.delete(save=False) for file in files])
    messages.success(request, _('Deleted %(key)s.') % {'key': key})
    return redirect(board)


def _act_attachment(request, ticket, forms):
    upload = request.FILES['file']
    if upload.size > attachments.MAX_BYTES:
        messages.error(
            request,
            _('%(name)s is larger than %(size)s MB.')
            % {'name': upload.name, 'size': attachments.MAX_BYTES // 1024 // 1024},
        )
    else:
        Attachment.from_upload(upload, request.user, ticket=ticket)
    return redirect(ticket)


# What the ticket page's forms post, by their `action`. Each answers a redirect when done, or None to show
# the page again with the form it bound, errors and all.
TICKET_ACTIONS = {
    'title': _act_on_text,
    'description': _act_on_text,
    'comment': _act_comment,
    'edit_comment': _act_edit_comment,
    'block': _act_block,
    'child': _act_child,
    'watch': _act_watch,
    'relation': _act_relation,
    'unrelate': _act_unrelate,
    'delete': _act_delete,
    'attachment': _act_attachment,
}


def _relations(ticket) -> list[dict]:
    """The ticket's relations both ways, each with the other ticket, marked when an open ticket blocks it."""
    relations = [
        {
            'kind': relation.get_type_display(),
            'other': relation.target,
            'relation': relation,
            'is_child': relation.type == Relation.Type.PARENT_OF,
        }
        for relation in ticket.outgoing_relations.select_related(
            'target__column__group',
            'target__assignee',
            'target__creator',
        ).prefetch_related('target__column__group__columns')
    ] + [
        {
            'kind': Relation.INVERSE_LABELS[relation.type],
            'other': relation.source,
            'relation': relation,
            'is_child': False,
        }
        for relation in ticket.incoming_relations.select_related(
            'source__column__group',
            'source__assignee',
            'source__creator',
        ).prefetch_related('source__column__group__columns')
    ]
    # The related tickets that an open ticket blocks, as the board marks them.
    others = [relation['other'] for relation in relations]
    blocked_ids = set(
        Relation.objects.filter(type=Relation.Type.BLOCKS, target__in=others)
        .exclude(source__column__category=Column.Category.DONE)
        .values_list('target_id', flat=True),
    )
    for other in others:
        other.has_open_blocker = other.pk in blocked_ids
    # In the board's order within each kind, so dragging a row moves the ticket on the board too.
    return sorted(relations, key=lambda relation: (relation['kind'], relation['other'].rank, relation['other'].pk))


@board_required
def ticket_detail(request, key):
    match = KEY_RE.match(key)
    if not match:
        raise Http404(f'No ticket {key}.')
    ticket = get_object_or_404(
        Ticket.objects.select_related('column__group', 'creator', 'assignee'),
        pk=int(match[1]),
    )
    forms = {
        'comment_form': CommentForm(instance=Comment(ticket=ticket, author=request.user)),
        'block_form': BlockForm(ticket=ticket),
        'relation_form': RelationForm(ticket=ticket),
        'child_form': ChildForm(),
        'title_form': TitleForm.for_ticket(ticket),
        'description_form': DescriptionForm.for_ticket(ticket),
    }
    if (action := request.POST.get('action')) is not None:
        if action not in TICKET_ACTIONS:
            raise Http404(f'Unknown action {action!r}')
        if response := TICKET_ACTIONS[action](request, ticket, forms):
            return response

    relations = _relations(ticket)
    # The main board on this ticket and everything under it, from Open on board beside its subtasks, to use
    # its filters on them. It opens on the ticket's own group; the All groups tab adds subtasks elsewhere.
    main_board_query = urlencode({'group': ticket.column.group.slug, 'parent': ticket.key})

    return render(
        request,
        'gilde_board/ticket_detail.html',
        {
            **forms,
            'ticket': ticket,
            'labels': ticket.labels.all(),
            'relations': relations,
            'done_relations': sum(item['other'].column.category == Column.Category.DONE for item in relations),
            'main_board_url': f'{reverse("gilde_board:board")}?{main_board_query}',
            'open_blockers': ticket.open_blockers(),
            'block_reason': ticket.comments.filter(sets_blocked=True).last() if ticket.is_blocked else None,
            'attachments': ticket.attachments.all(),
            'named_in': backlinks.find(request, ticket.key),
            # Pull requests first, then branches, then commits; newest first within each.
            'code_references': sorted(
                ticket.code_references.all(),
                key=lambda reference: CODE_KIND_ORDER.index(reference.kind),
            ),
            'feed': build_feed(ticket),
            'watchers': [watcher.user for watcher in ticket.watchers.select_related('user')],
            'mention_handle': people.handle(request.user),
            'groups': Group.objects.all(),
            'users': people.members(SCOPE),
            'sizes': Ticket.Size.choices,
            'label_names': json.dumps(list(Label.objects.values_list('name', flat=True))),
            'display_timezone': settings.GILDE_BOARD_DISPLAY_TIMEZONE,
            'board_url': _board_url(request, ticket.column.group),
        },
    )


@board_required
def ticket_peek(request, key):
    """A ticket in brief, for the panel that shows it beside the board or a ticket page (peek.js)."""
    match = KEY_RE.match(key)
    if not match:
        raise Http404(f'Unknown ticket key {key!r}')
    ticket = get_object_or_404(
        Ticket.objects.select_related('column__group', 'creator', 'assignee'),
        pk=int(match[1]),
    )
    relations = [
        {'kind': relation.get_type_display(), 'other': relation.target}
        for relation in ticket.outgoing_relations.select_related('target__column')
    ] + [
        {'kind': Relation.INVERSE_LABELS[relation.type], 'other': relation.source}
        for relation in ticket.incoming_relations.select_related('source__column')
    ]
    return render(
        request,
        'gilde_board/_peek.html',
        {
            'ticket': ticket,
            'labels': ticket.labels.all(),
            'relations': sorted(
                relations,
                key=lambda relation: (relation['kind'], relation['other'].rank, relation['other'].pk),
            ),
            'open_blockers': ticket.open_blockers(),
            'comments': ticket.comments.select_related('author').order_by('-created_at', '-pk')[:PEEK_COMMENTS],
            'comment_count': ticket.comments.count(),
            'display_timezone': settings.GILDE_BOARD_DISPLAY_TIMEZONE,
        },
    )


@board_required
@require_POST
def attachment_upload(request):
    """Image upload endpoint of the Markdown editor."""
    ticket = get_object_or_404(Ticket, pk=int(request.GET['ticket'])) if request.GET.get('ticket') else None

    def create(upload):
        return Attachment.from_upload(upload, request.user, ticket=ticket)

    return attachments.editor_upload(request, create)


@board_required
def attachment(request, pk, name=None):
    return attachments.serve(get_object_or_404(Attachment, pk=pk))


@board_required
def group_create(request):
    """A new group, from the tab beside the board's groups; its columns are added on its settings page."""
    form = GroupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        group = form.save()
        return redirect('gilde_board:group_edit', slug=group.slug)
    return render(request, 'gilde_board/group_create.html', {'form': form})


@board_required
def group_edit(request, slug):
    group = get_object_or_404(Group, slug=slug)
    form = GroupForm(request.POST or None, instance=group, prefix='group')
    formset = ColumnFormSet(request.POST or None, instance=group, prefix='columns')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            group = form.save()
            formset.save()
        messages.success(request, _('Saved %(group)s.') % {'group': group})
        return redirect('gilde_board:group_edit', slug=group.slug)
    return render(
        request,
        'gilde_board/group_edit.html',
        {
            'group': group,
            'form': form,
            'formset': formset,
            'ticket_count': Ticket.objects.filter(column__group=group).count(),
            'other_groups': Group.objects.exclude(pk=group.pk),
        },
    )


@board_required
@require_POST
def group_delete(request, slug):
    """Delete a group with its columns, first moving any tickets left in it to the group in `move_to`.

    Each ticket goes to the matching column there, keeping its place in the order of all tickets, and
    its history records the move. Every ticket moves in a transaction of its own: a request cut short
    (Heroku stops one at 30 seconds) leaves each ticket either moved or untouched, never half of it, and
    the group is only deleted once it is empty, so doing it again moves the rest.
    """
    group = get_object_or_404(Group, slug=slug)
    remaining = list(Ticket.objects.filter(column__group=group).select_related('column'))
    if remaining:
        if not request.POST.get('move_to'):
            messages.error(
                request,
                _('%(group)s still holds %(count)s tickets; choose a group to move them to.')
                % {'group': group, 'count': len(remaining)},
            )
            return redirect('gilde_board:group_edit', slug=group.slug)
        target = get_object_or_404(Group.objects.exclude(pk=group.pk), pk=int(request.POST['move_to']))
        if not target.columns.exists():
            messages.error(request, _('%(group)s has no columns yet.') % {'group': target})
            return redirect('gilde_board:group_edit', slug=group.slug)
        for ticket in remaining:
            with transaction.atomic():
                ticket.column = target.matching_column(ticket.column)
                ticket.save()
    group.delete()
    if remaining:
        done = _('Deleted %(group)s and moved its %(count)s tickets to %(target)s.')
        messages.success(request, done % {'group': group, 'count': len(remaining), 'target': target})
    else:
        messages.success(request, _('Deleted %(group)s.') % {'group': group})
    return redirect('gilde_board:board')


@csrf_exempt
@require_POST
def github_webhook(request):
    """Records what GitHub reports about the repository: pushes to its default branch, pull requests
    and new branches (tickets/github.py).

    GitHub calls this without a login, so the request proves itself instead: its X-Hub-Signature-256 is
    the body signed with GILDE_BOARD_GITHUB_WEBHOOK_SECRET. Other events, such as the ping on setting the
    webhook up, are acknowledged and ignored.
    """
    # Without a secret anybody could sign a delivery, so nothing is accepted until one is set.
    if not settings.GILDE_BOARD_GITHUB_WEBHOOK_SECRET:
        return HttpResponse(status=403)
    expected = (
        'sha256='
        + hmac.new(settings.GILDE_BOARD_GITHUB_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(request.headers.get('X-Hub-Signature-256', ''), expected):
        return HttpResponse(status=403)
    event = request.headers.get('X-GitHub-Event', '')
    return JsonResponse({'recorded': github.handle_event(event, json.loads(request.body))})
