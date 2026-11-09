from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from datagroceries.core import attachments, markdown, people
from datagroceries.wiki import access, export, operations, search, versions
from datagroceries.wiki.access import READ, WRITE
from datagroceries.wiki.compare import side_by_side
from datagroceries.wiki.conf import SCOPE
from datagroceries.wiki.forms import (
    ArrangeForm,
    CommentForm,
    MoveForm,
    NewPageForm,
    PageForm,
    StartPageForm,
    TranslateForm,
    fingerprint,
)
from datagroceries.wiki.models import TOP, Attachment, Comment, Page, slug_of
from datagroceries.wiki.templatetags.dg_wiki import render_context, tree_context

wiki_required = people.may_use_required(SCOPE)

# How many headings a page needs before a table of contents beside it helps.
CONTENTS_FROM = 3
RECENT_PAGES = 15


def _last_change(page: Page):
    """The newest history record of the page, which says who last changed it, when, and how."""
    return page.history.select_related('history_user').first()


@wiki_required
def home(request):
    recent = access.pages(request.user).order_by('-updated_at')[:RECENT_PAGES]
    return render(request, 'dg_wiki/home.html', {'recent': recent})


@wiki_required
def page_search(request):
    query = request.GET.get('q', '').strip()
    hits = search.search(query, access.pages(request.user)) if query else []
    return render(request, 'dg_wiki/search.html', {'query': query, 'hits': hits, 'most': search.MAX_HITS})


@wiki_required
def page(request, path):
    found = Page.objects.select_related('parent').filter(path=path).first()
    if found is None:
        if former := access.former(request.user, path):
            return redirect(former)
        return _missing(request, path)
    if not access.may(request.user, READ, found):
        raise Http404(f'No page {path}.')
    if found.folder != (request.resolver_match.url_name == 'folder'):
        return redirect(found)
    readable, hidden = access.pages(request.user), access.hidden(request.user)
    can = access.rights(request.user, found)
    html, headings = markdown.render_document(found.body, context=render_context(found))
    last_change = _last_change(found)
    context = {
        'page': found,
        'html': html,
        'headings': headings if len(headings) >= CONTENTS_FROM else [],
        'ancestors': found.ancestors(),
        'children': readable.filter(parent=found),
        'attachments': found.attachments.all(),
        'backlinks': readable.filter(links__target=found).exclude(pk=found.pk).order_by('title').distinct(),
        'last_change': last_change,
        'last_changed_by': versions.name(versions.changed_by(found, last_change)),
        'last_changed_via': versions.via(last_change),
        'comments': _comments(found),
        'comment_form': CommentForm(page=found),
        'watchers': access.readers(found, [watcher.user for watcher in found.watchers.select_related('user')]),
        'translations': [each for each in found.translation_group() if each.pk != found.pk and each.pk not in hidden],
        'can': can,
        'can_translate': len(settings.LANGUAGES) > len(found.translation_group())
        and access.may(request.user, WRITE, found.parent or TOP),
        # A translation older than the latest change to its original may say something else by now.
        'behind': found.original
        if found.original and found.original.updated_at > found.updated_at and found.original.pk not in hidden
        else None,
    }
    return render(request, 'dg_wiki/page.html', context)


def _title(slug: str) -> str:
    """A title for the page at an address that has none yet, from the end of the address."""
    return slug.replace('-', ' ').strip().capitalize()


def _missing(request, path):
    """The address of no page: an offer to start it there, under the pages above it, with the title a
    link to it gave, or else one from the address, to whoever may write there; as a folder at a folder's
    address, ending in "/". A page above it that is not there either is to be started first, the highest
    first, and one that is a page made a folder; an address that is not all slugs no title gives. Under a
    page the person may not see, the address is not found."""
    parts = path.split('/')
    above = ['/'.join(parts[:end]) for end in range(1, len(parts))]
    found = {page.path: page for page in Page.objects.filter(path__in=above)}
    if any(page.pk in access.hidden(request.user) for page in found.values()):
        raise Http404(f'No page {path}.')
    ancestors = [found[each] for each in above if each in found]
    absent = next((each for each in above if each not in found), None)
    parent = ancestors[-1] if ancestors else None
    not_folder = parent if parent and not parent.folder else None
    folder = request.resolver_match.url_name == 'folder'
    possible = absent is None and not not_folder and all(part and slug_of(part) == part for part in parts)
    allowed = access.may(request.user, WRITE, parent or TOP)
    title = request.GET.get('title') or _title(parts[-1])
    data = request.POST if request.method == 'POST' else None
    form = StartPageForm(data, initial={'title': title}, path=path, parent=parent)
    if possible and allowed and form.is_valid():
        created = operations.create(request, form.cleaned_data['title'], parent, folder=folder)
        return redirect('dg_wiki:page_edit', created.path)
    context = {
        'folder': folder,
        'not_folder': not_folder,
        'form': form if possible and allowed else None,
        'possible': possible,
        'path': path,
        'ancestors': ancestors,
        'parent': parent,
        'absent': absent and {'path': absent, 'title': _title(absent.rpartition('/')[2])},
    }
    return render(request, 'dg_wiki/missing.html', context, status=404)


@wiki_required
def page_create(request):
    if request.method == 'POST':
        form = NewPageForm(request.POST, user=request.user)
        if form.is_valid():
            created = operations.create(request, form.cleaned_data['title'], form.cleaned_data['parent'])
            return redirect('dg_wiki:page_edit', created.path)
    else:
        form = NewPageForm(
            initial={'parent': request.GET.get('parent'), 'title': request.GET.get('title', '')}, user=request.user
        )
        if not form.fields['parent'].choices:
            raise PermissionDenied
    return render(request, 'dg_wiki/page_create.html', {'form': form})


@wiki_required
def page_edit(request, path):
    edited = access.page(request.user, path)
    access.require(request.user, WRITE, edited)
    if request.method != 'POST':
        form = PageForm(instance=edited)
        return render(request, 'dg_wiki/page_edit.html', {'page': edited, 'form': form})
    with transaction.atomic():
        stored = Page.objects.select_for_update().get(pk=edited.pk)
        form = PageForm(request.POST, instance=stored)
        if form.is_valid():
            if form.cleaned_data['original'] == fingerprint(Page.objects.get(pk=stored.pk)):
                data = form.cleaned_data
                operations.write(request, stored, data['title'], data['body'], data['language'])
                return redirect(stored)
            form.add_error(
                None,
                _(
                    '%(who)s saved this page while you were editing it. Your text is still here: open the page '
                    'in another tab to see theirs, put the two together, and save again to replace theirs.'
                )
                % {'who': versions.name(_last_change(stored).history_user)},
            )
            # The next save is made knowing what it replaces.
            form.data = form.data.copy()
            form.data['original'] = fingerprint(Page.objects.get(pk=stored.pk))
    return render(request, 'dg_wiki/page_edit.html', {'page': edited, 'form': form})


@wiki_required
def page_move(request, path):
    moved = access.page(request.user, path)
    access.require(request.user, WRITE, moved)
    form = MoveForm(request.POST or None, page=moved, user=request.user)
    if request.method == 'POST' and form.is_valid():
        operations.move(request, moved, form.cleaned_data['parent'])
        return redirect(moved)
    return render(request, 'dg_wiki/page_move.html', {'page': moved, 'form': form, 'ancestors': moved.ancestors()})


@wiki_required
@require_POST
def page_delete(request, path):
    deleted = access.page(request.user, path)
    try:
        operations.delete(request, deleted)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect(deleted)
    messages.success(request, _('“%(title)s” is deleted.') % {'title': deleted.title})
    return redirect(deleted.parent or 'dg_wiki:home')


@wiki_required
@require_POST
def page_folder(request, path):
    """Make the page a folder, or a folder with no pages in it a page again."""
    shown = access.page(request.user, path)
    try:
        operations.make_folder(request, shown, request.POST.get('folder') == 'yes')
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return redirect(shown)


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
    current = access.pages(request.user).filter(pk=request.POST.get('current') or None).first()
    tree = render_to_string('dg_wiki/_tree.html', tree_context(request.user, current, also_open=page), request)
    return JsonResponse({'tree': tree, 'url': current.get_absolute_url() if current else None})


@wiki_required
def page_history(request, path):
    """Every version of the page, newest first, with who made it and what it changed."""
    shown = access.page(request.user, path)
    context = {
        'page': shown,
        'ancestors': shown.ancestors(),
        'versions': versions.of(shown),
        'can': access.rights(request.user, shown),
    }
    return render(request, 'dg_wiki/page_history.html', context)


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
    shown = access.page(request.user, path)
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
        {'record': each, 'by': versions.name(versions.changed_by(shown, each)), 'current': _says(shown, each)}
        if each
        else None
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
        'can': access.rights(request.user, shown),
    }
    return render(request, 'dg_wiki/page_compare.html', context)


@wiki_required
@require_POST
def page_restore(request, path, version):
    shown = access.page(request.user, path)
    record = get_object_or_404(shown.history, history_id=version)
    operations.restore(request, shown, record)
    messages.success(request, _('The version of %(when)s is back.') % {'when': versions.when(record.history_date)})
    return redirect(shown)


@wiki_required
@require_POST
def page_upload(request, path):
    """Where the Markdown editor uploads the images pasted or dropped into a page's text."""
    shown = access.page(request.user, path)
    return attachments.editor_upload(request, lambda upload: operations.attach(request, shown, upload))


@wiki_required
@require_POST
def page_attach(request, path):
    """A file put beside the page."""
    shown = access.page(request.user, path)
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
    return attachments.serve(get_object_or_404(Attachment.objects.exclude(page__in=access.hidden(request.user)), pk=pk))


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
            each.via, each.edited = versions.via(created.get(each.pk)), each.pk in edited
    return comments


@wiki_required
@require_POST
def comment_create(request, path):
    shown = access.page(request.user, path)
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
    shown = access.page(request.user, path)
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
    shown = access.page(request.user, path)
    operations.watch(request, shown, request.POST.get('watching') == 'yes')
    return redirect(f'{shown.get_absolute_url()}#comments')


def _download(content, name: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{name}"'
    return response


@wiki_required
def page_export(request, path):
    """The page as a Markdown file; with the pages under it, as a zip of them all."""
    shown = access.page(request.user, path)
    if shown.children.exists():
        return _download(export.tree_zip(request, shown), f'{shown.slug}.zip', 'application/zip')
    return _download(export.page_markdown(request, shown), f'{shown.slug}.md', 'text/markdown; charset=utf-8')


@wiki_required
def wiki_export(request):
    """Every page, as a zip of Markdown files."""
    return _download(export.tree_zip(request, None), 'wiki.zip', 'application/zip')


@wiki_required
def page_translate(request, path):
    """A translation of the page, beside it, which opens in the editor with the page's text to translate."""
    shown = access.page(request.user, path)
    access.require(request.user, WRITE, shown.parent or TOP)
    form = TranslateForm(request.POST or None, page=shown)
    if request.method == 'POST' and form.is_valid():
        made = operations.translate(request, shown, form.cleaned_data['language'], form.cleaned_data['title'])
        return redirect('dg_wiki:page_edit', made.path)
    return render(request, 'dg_wiki/page_translate.html', {'page': shown, 'form': form, 'ancestors': shown.ancestors()})
