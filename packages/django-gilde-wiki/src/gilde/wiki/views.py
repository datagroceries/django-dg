from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from gilde.core import markdown, people
from gilde.wiki import operations
from gilde.wiki.conf import SCOPE
from gilde.wiki.forms import MoveForm, NewPageForm, PageForm, fingerprint
from gilde.wiki.models import FormerPath, Page

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
    html, headings = markdown.render_document(found.body)
    last_change = _last_change(found)
    context = {
        'page': found,
        'html': html,
        'headings': headings if len(headings) >= CONTENTS_FROM else [],
        'ancestors': found.ancestors(),
        'children': found.children.all(),
        'last_change': last_change,
        'last_changed_by': _name(_changed_by(found, last_change)),
        'last_changed_via': _via(last_change),
    }
    return render(request, 'gilde_wiki/page.html', context)


def _missing(request, path):
    """The address of no page: an offer to start it, under the page the address goes through, if any."""
    parent_path, _slash, slug = path.rpartition('/')
    parent = Page.objects.filter(path=parent_path).first() if parent_path else None
    title = slug.replace('-', ' ').strip().capitalize()
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
