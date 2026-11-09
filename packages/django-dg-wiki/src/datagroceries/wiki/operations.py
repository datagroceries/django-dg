"""What the wiki's pages and its API both do to pages, so both follow the same rules: who may do it
(datagroceries.wiki.access) is checked here, and the callers find only pages their person may read.
Validation stays with the callers: the pages' forms."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from datagroceries.wiki import access, notifications
from datagroceries.wiki.access import COMMENT, WRITE
from datagroceries.wiki.models import TOP, Attachment, Comment, Page


def _last_position(parent: Page | None) -> int:
    return (Page.objects.filter(parent=parent).aggregate(last=Max('position'))['last'] or 0) + 1


def create(request, title: str, parent: Page | None = None, body: str = '') -> Page:
    """A new page by the requesting user, the last of the pages under `parent`, or at the top."""
    access.require(request.user, WRITE, parent or TOP)
    with transaction.atomic():
        page = Page.objects.create(
            title=title, parent=parent, body=body, creator=request.user, position=_last_position(parent)
        )
        notifications.written(request, page, '')
    access.forget()
    return page


def write(request, page: Page, title: str, body: str, language: str | None = None):
    """A new title and text, and language unless it is None; a new title gives the page a new address. The
    people newly @-mentioned in the text hear about it."""
    access.require(request.user, WRITE, page)
    before = Page.objects.values_list('body', flat=True).get(pk=page.pk)
    page.title, page.body = title, body
    if language is not None:
        page.language = language
    with transaction.atomic():
        page.save()
        notifications.written(request, page, before)


def move(request, page: Page, parent: Page | None):
    """Put the page, with everything under it, last under `parent`, or at the top."""
    if parent != page.parent:
        arrange(request, page, parent)


def arrange(request, page: Page, parent: Page | None, before: Page | None = None):
    """Put the page, with everything under it, under `parent`, or at the top, just before `before`, one
    of the pages there, or after them all. Only a page that changes parent gets a history record: the
    order of pages is not kept in their history. Putting a page somewhere needs write on it and there."""
    access.require(request.user, WRITE, page)
    access.require(request.user, WRITE, parent or TOP)
    with transaction.atomic():
        siblings = list(Page.objects.filter(parent=parent).exclude(pk=page.pk))
        siblings.insert(siblings.index(before) if before in siblings else len(siblings), page)
        for position, sibling in enumerate(siblings, start=1):
            sibling.position = position
        Page.objects.bulk_update([sibling for sibling in siblings if sibling.pk != page.pk], ['position'])
        if page.parent_id != (parent.pk if parent else None):
            page.parent = parent
            page.save()
            access.forget()
        else:
            Page.objects.filter(pk=page.pk).update(position=page.position)


def restore(request, page: Page, version):
    """Make the page say again what it said in `version`, one of its history records: its title and
    text, not its place in the tree. A version of its own, so nothing is lost."""
    access.require(request.user, WRITE, page)
    before = page.body
    page.title, page.body = version.title, version.body
    page.restored_from = version.history_id
    try:
        with transaction.atomic():
            page.save()
            notifications.written(request, page, before)
    finally:
        del page.restored_from


def attach(request, page: Page, upload) -> Attachment:
    access.require(request.user, WRITE, page)
    return Attachment.from_upload(upload, request.user, page=page)


def translate(request, page: Page, language: str, title: str) -> Page:
    """A translation of the page into `language`, beside it, starting from its text to translate."""
    access.require(request.user, WRITE, page.parent or TOP)
    with transaction.atomic():
        made = Page.objects.create(
            title=title,
            parent=page.parent,
            body=page.body,
            language=language,
            original=page.original or page,
            creator=request.user,
            position=_last_position(page.parent),
        )
        notifications.watch(made, request.user)
    access.forget()
    return made


def delete(request, page: Page):
    """Delete a page that has no pages under it, and its files; its history stays. The first of its
    translations becomes the original of the others."""
    access.require(request.user, WRITE, page)
    if page.children.exists():
        raise ValidationError(_('Move or delete the pages under this page first.'))
    with transaction.atomic():
        translations = list(page.translations.order_by('pk'))
        if translations:
            Page.objects.filter(pk__in=[each.pk for each in translations[1:]]).update(original=translations[0])
            Page.objects.filter(pk=translations[0].pk).update(original=None)
        files = [attachment.file for attachment in page.attachments.all()]
        page.delete()
        transaction.on_commit(lambda: [file.delete(save=False) for file in files])


def comment(request, page: Page, body: str, parent: Comment | None = None) -> Comment:
    """A comment by the requesting user, or a reply to `parent`; the people it mentions and the page's
    watchers hear about it."""
    access.require(request.user, COMMENT, page)
    with transaction.atomic():
        made = Comment.objects.create(page=page, author=request.user, body=body, parent=parent)
        notifications.commented(request, made)
    return made


def edit_comment(request, comment: Comment, body: str):
    """Change a comment's text. Only the people it newly mentions hear about it: the watchers had the first
    version, and the comment now shows as edited."""
    access.require(request.user, COMMENT, comment.page)
    before = comment.body
    comment.body = body
    with transaction.atomic():
        comment.save()
        notifications.commented(request, comment, before)


def watch(request, page: Page, watching: bool):
    if watching:
        notifications.watch(page, request.user)
    else:
        page.watchers.filter(user=request.user).delete()
