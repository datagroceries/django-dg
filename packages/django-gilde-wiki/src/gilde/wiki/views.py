from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from gilde.core import attachments, markdown, people
from gilde.wiki import operations
from gilde.wiki.compare import side_by_side
from gilde.wiki.conf import SCOPE
from gilde.wiki.forms import ArrangeForm, CommentForm, MoveForm, NewPageForm, PageForm, fingerprint
from gilde.wiki.models import Attachment, Comment, FormerPath, Page
from gilde.wiki.templatetags.gilde_wiki import render_context, tree_context

wiki_required = people.may_use_required(SCOPE)

# How many headings a page needs before a table of contents beside it helps.
CONTENTS_FROM = 3
RECENT_PAGES = 15


def _page(path: str) -> Page:
    return get_object_or_404(Page.objects.select_related('parent'), path=path)


def _last_change(page: Page):
    """The newest history record of the page, which says who last changed it, when, and how."""
    return page.history.select_related('history_user').first()


def _changed_by(page: Page, record):
    """Who made the change `record` holds. A page made outside a request, as by a script, has no one in
    its first record, but has its creator."""
    if record is None:
        return None
    return record.history_user or (page.creator if record.history_type == '+' else None)


def _name(user) -> str:
    return people.name(user) if user else _('Someone')


def _via(record) -> str:
    """The history keeps "via Claude Code on my laptop" in English; it shows in the reader's language."""
    reason = (record.history_change_reason or '') if record else ''
    return _('via %(name)s') % {'name': reason.removeprefix('via ')} if reason.startswith('via ') else ''


@wiki_required
def home(request):
    recent = Page.objects.order_by('-updated_at')[:RECENT_PAGES]
    return render(request, 'gilde_wiki/home.html', {'recent': recent})


@wiki_required
def page(request, path):
    found = Page.objects.select_related('parent').filter(path=path).first()
    if found is None:
        former = FormerPath.objects.select_related('page').filter(path=path).first()
        if former is not None:
            return redirect(former.page)
        return _missing(request, path)
    html, headings = markdown.render_document(found.body, context=render_context(found))
    last_change = _last_change(found)
    context = {
        'page': found,
        'html': html,
        'headings': headings if len(headings) >= CONTENTS_FROM else [],
        'ancestors': found.ancestors(),
        'children': found.children.all(),
        'attachments': found.attachments.all(),
        'backlinks': Page.objects.filter(links__target=found).exclude(pk=found.pk).order_by('title').distinct(),
        'last_change': last_change,
        'last_changed_by': _name(_changed_by(found, last_change)),
        'last_changed_via': _via(last_change),
        'comments': _comments(found),
        'comment_form': CommentForm(page=found),
        'watchers': [watcher.user for watcher in found.watchers.select_related('user')],
    }
    return render(request, 'gilde_wiki/page.html', context)


def _missing(request, path):
    """The address of no page: an offer to start it, under the page the address goes through, if any,
    with the title a link to it gave, or else one from the address."""
    parent_path, _slash, slug = path.rpartition('/')
    parent = Page.objects.filter(path=parent_path).first() if parent_path else None
    title = request.GET.get('title') or slug.replace('-', ' ').strip().capitalize()
    form = NewPageForm(initial={'title': title, 'parent': parent.pk if parent else None})
    return render(request, 'gilde_wiki/missing.html', {'form': form, 'path': path}, status=404)


@wiki_required
def page_create(request):
    if request.method == 'POST':
        form = NewPageForm(request.POST)
        if form.is_valid():
            created = operations.create(request, form.cleaned_data['title'], form.cleaned_data['parent'])
            return redirect('gilde_wiki:page_edit', created.path)
    else:
        form = NewPageForm(initial={'parent': request.GET.get('parent'), 'title': request.GET.get('title', '')})
    return render(request, 'gilde_wiki/page_create.html', {'form': form})


@wiki_required
def page_edit(request, path):
    edited = _page(path)
    if request.method != 'POST':
        form = PageForm(instance=edited)
        return render(request, 'gilde_wiki/page_edit.html', {'page': edited, 'form': form})
    with transaction.atomic():
        stored = Page.objects.select_for_update().get(pk=edited.pk)
        form = PageForm(request.POST, instance=stored)
        if form.is_valid():
            if form.cleaned_data['original'] == fingerprint(Page.objects.get(pk=stored.pk)):
                operations.write(request, stored, form.cleaned_data['title'], form.cleaned_data['body'])
                return redirect(stored)
            form.add_error(
                None,
                _(
                    '%(who)s saved this page while you were editing it. Your text is still here: open the page '
                    'in another tab to see theirs, put the two together, and save again to replace theirs.'
                )
                % {'who': _name(_last_change(stored).history_user)},
            )
            # The next save is made knowing what it replaces.
            form.data = form.data.copy()
            form.data['original'] = fingerprint(Page.objects.get(pk=stored.pk))
    return render(request, 'gilde_wiki/page_edit.html', {'page': edited, 'form': form})


@wiki_required
def page_move(request, path):
    moved = _page(path)
    form = MoveForm(request.POST or None, page=moved)
    if request.method == 'POST' and form.is_valid():
        operations.move(request, moved, form.cleaned_data['parent'])
        return redirect(moved)
    return render(request, 'gilde_wiki/page_move.html', {'page': moved, 'form': form, 'ancestors': moved.ancestors()})


@wiki_required
@require_POST
def page_delete(request, path):
    deleted = _page(path)
    try:
        operations.delete(request, deleted)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect(deleted)
    messages.success(request, _('“%(title)s” is deleted.') % {'title': deleted.title})
    return redirect(deleted.parent or 'gilde_wiki:home')


@wiki_required
@require_POST
def tree_arrange(request):
    """A page dragged in the tree. The answer is the tree as it is now, and where the page shown, `current`,
    is now, as dragging it or a page above it moves it."""
    form = ArrangeForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errors': [error for errors in form.errors.values() for error in errors]}, status=400)
    page = form.cleaned_data['page']
    operations.arrange(request, page, form.cleaned_data['parent'], form.cleaned_data['before'])
    current = Page.objects.filter(pk=request.POST.get('current') or None).first()
    tree = render_to_string('gilde_wiki/_tree.html', tree_context(current, also_open=page), request)
    return JsonResponse({'tree': tree, 'url': current.get_absolute_url() if current else None})


def _when(moment) -> str:
    return formats.date_format(timezone.localtime(moment), 'SHORT_DATETIME_FORMAT')


def _changes(record, previous, earlier: dict, parents: dict) -> list[str]:
    """What `record` changed since `previous`, the version before it, in words."""
    if previous is None:
        return [_('Created')]
    if record.restored_from:
        restored = earlier.get(record.restored_from)
        return [_('Brought back the version of %(when)s') % {'when': _when(restored.history_date) if restored else '?'}]
    changes = []
    if record.title != previous.title:
        changes.append(_('Renamed to “%(title)s”') % {'title': record.title})
    if record.body != previous.body:
        changes.append(_('Text changed'))
    if record.parent_id != previous.parent_id:
        parent = parents.get(record.parent_id)
        changes.append(_('Moved under “%(title)s”') % {'title': parent.title} if parent else _('Moved to the top'))
    return changes


@wiki_required
def page_history(request, path):
    """Every version of the page, newest first, with who made it and what it changed."""
    shown = _page(path)
    records = list(shown.history.select_related('history_user'))
    earlier = {record.history_id: record for record in records}
    parents = Page.objects.in_bulk({record.parent_id for record in records if record.parent_id})
    versions = [
        {
            'record': record,
            'previous': previous,
            'by': _name(_changed_by(shown, record)),
            'via': _via(record),
            'changes': _changes(record, previous, earlier, parents),
        }
        for record, previous in zip(records, [*records[1:], None], strict=True)
    ]
    context = {'page': shown, 'ancestors': shown.ancestors(), 'versions': versions}
    return render(request, 'gilde_wiki/page_history.html', context)


def _before(page: Page, record):
    """The version of the page just before `record`, if any."""
    same_moment = Q(history_date=record.history_date, history_id__lt=record.history_id)
    return page.history.filter(Q(history_date__lt=record.history_date) | same_moment).first()


def _says(page: Page, record) -> bool:
    """Whether the page says now what it said in `record`."""
    return (record.title, record.body) == (page.title, page.body)


@wiki_required
def page_compare(request, path, version):
    """A version of the page beside the one before it, or beside the version `with` names."""
    shown = _page(path)
    record = get_object_or_404(shown.history.select_related('history_user'), history_id=version)
    if request.GET.get('with'):
        other = get_object_or_404(shown.history.select_related('history_user'), history_id=request.GET['with'])
    else:
        other = _before(shown, record)
    if other is None:
        older, newer = None, record
    else:
        older, newer = sorted([other, record], key=lambda each: (each.history_date, each.history_id))
    sides = [
        {'record': each, 'by': _name(_changed_by(shown, each)), 'current': _says(shown, each)} if each else None
        for each in (older, newer)
    ]
    context = {
        'page': shown,
        'ancestors': shown.ancestors(),
        'older': sides[0],
        'newer': sides[1],
        'title_changed': older is not None and older.title != newer.title,
        'rows': side_by_side(older.body if older else '', newer.body),
        'latest': shown.history.first(),
    }
    return render(request, 'gilde_wiki/page_compare.html', context)


@wiki_required
@require_POST
def page_restore(request, path, version):
    shown = _page(path)
    record = get_object_or_404(shown.history, history_id=version)
    operations.restore(request, shown, record)
    messages.success(request, _('The version of %(when)s is back.') % {'when': _when(record.history_date)})
    return redirect(shown)


@wiki_required
@require_POST
def page_upload(request, path):
    """Where the Markdown editor uploads the images pasted or dropped into a page's text."""
    shown = _page(path)
    return attachments.editor_upload(request, lambda upload: operations.attach(request, shown, upload))


@wiki_required
@require_POST
def page_attach(request, path):
    """A file put beside the page."""
    shown = _page(path)
    upload = request.FILES.get('file')
    if upload is not None and upload.size > attachments.MAX_BYTES:
        messages.error(
            request,
            _('%(name)s is larger than %(size)s MB.')
            % {'name': upload.name, 'size': attachments.MAX_BYTES // 1024 // 1024},
        )
    elif upload is not None:
        operations.attach(request, shown, upload)
    return redirect(shown)


@wiki_required
def attachment(request, pk, name):
    return attachments.serve(get_object_or_404(Attachment, pk=pk))


def _comments(page: Page) -> list[Comment]:
    """The page's comments, oldest first, each with its replies; each says through which agent it was
    written (`via`) and whether it was changed after (`edited`)."""
    comments = list(page.comments.filter(parent=None).select_related('author').prefetch_related('replies__author'))
    ids = [comment.pk for comment in page.comments.all()]
    records = Comment.history.filter(id__in=ids)
    created = {record.id: record for record in records.filter(history_type='+')}
    edited = set(records.filter(history_type='~').values_list('id', flat=True))
    for comment in comments:
        for each in (comment, *comment.replies.all()):
            each.via, each.edited = _via(created.get(each.pk)), each.pk in edited
    return comments


@wiki_required
@require_POST
def comment_create(request, path):
    shown = _page(path)
    form = CommentForm(request.POST, page=shown)
    if not form.is_valid():
        messages.error(request, _('A comment needs text.'))
        return redirect(f'{shown.get_absolute_url()}#comments')
    made = operations.comment(request, shown, form.cleaned_data['body'], form.cleaned_data['parent'])
    return redirect(made)


@wiki_required
@require_POST
def comment_edit(request, path, pk):
    """Only by its author."""
    shown = _page(path)
    edited = get_object_or_404(shown.comments, pk=pk, author=request.user)
    body = request.POST.get('body', '').strip()
    if body:
        operations.edit_comment(request, edited, body)
    else:
        messages.error(request, _('A comment needs text; the old one is kept.'))
    return redirect(edited)


@wiki_required
@require_POST
def page_watch(request, path):
    shown = _page(path)
    operations.watch(request, shown, request.POST.get('watching') == 'yes')
    return redirect(f'{shown.get_absolute_url()}#comments')
