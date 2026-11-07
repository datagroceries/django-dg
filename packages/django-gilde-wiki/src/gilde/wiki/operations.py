"""What the wiki's pages and, in time, its API both do to pages, so both follow the same rules. Validation
stays with the callers: the pages' forms."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from gilde.wiki import notifications
from gilde.wiki.models import Attachment, Comment, Page


def _last_position(parent: Page | None) -> int:
    return (Page.objects.filter(parent=parent).aggregate(last=Max('position'))['last'] or 0) + 1


def create(request, title: str, parent: Page | None = None, body: str = '') -> Page:
    """A new page by the requesting user, the last of the pages under `parent`, or at the top."""
    with transaction.atomic():
        page = Page.objects.create(
            title=title, parent=parent, body=body, creator=request.user, position=_last_position(parent)
        )
        notifications.written(request, page, '')
    return page


def write(request, page: Page, title: str, body: str):
    """A new title and text; a new title gives the page a new address. The people newly @-mentioned in the
    text hear about it."""
    before = Page.objects.values_list('body', flat=True).get(pk=page.pk)
    page.title, page.body = title, body
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
    order of pages is not kept in their history."""
    with transaction.atomic():
        siblings = list(Page.objects.filter(parent=parent).exclude(pk=page.pk))
        siblings.insert(siblings.index(before) if before in siblings else len(siblings), page)
        for position, sibling in enumerate(siblings, start=1):
            sibling.position = position
        Page.objects.bulk_update([sibling for sibling in siblings if sibling.pk != page.pk], ['position'])
        if page.parent_id != (parent.pk if parent else None):
            page.parent = parent
            page.save()
        else:
            Page.objects.filter(pk=page.pk).update(position=page.position)


def restore(request, page: Page, version):
    """Make the page say again what it said in `version`, one of its history records: its title and
    text, not its place in the tree. A version of its own, so nothing is lost."""
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
    return Attachment.from_upload(upload, request.user, page=page)


def delete(request, page: Page):
    """Delete a page that has no pages under it, and its files; its history stays."""
    if page.children.exists():
        raise ValidationError(_('Move or delete the pages under this page first.'))
    with transaction.atomic():
        files = [attachment.file for attachment in page.attachments.all()]
        page.delete()
        transaction.on_commit(lambda: [file.delete(save=False) for file in files])


def comment(request, page: Page, body: str, parent: Comment | None = None) -> Comment:
    """A comment by the requesting user, or a reply to `parent`; the people it mentions and the page's
    watchers hear about it."""
    with transaction.atomic():
        made = Comment.objects.create(page=page, author=request.user, body=body, parent=parent)
        notifications.commented(request, made)
    return made


def edit_comment(request, comment: Comment, body: str):
    """Change a comment's text. Only the people it newly mentions hear about it: the watchers had the first
    version, and the comment now shows as edited."""
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
