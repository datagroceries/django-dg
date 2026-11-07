"""What the wiki's pages and, in time, its API both do to pages, so both follow the same rules. Validation
stays with the callers: the pages' forms."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from gilde.wiki.models import Page


def _last_position(parent: Page | None) -> int:
    return (Page.objects.filter(parent=parent).aggregate(last=Max('position'))['last'] or 0) + 1


def create(request, title: str, parent: Page | None = None, body: str = '') -> Page:
    """A new page by the requesting user, the last of the pages under `parent`, or at the top."""
    with transaction.atomic():
        return Page.objects.create(
            title=title, parent=parent, body=body, creator=request.user, position=_last_position(parent)
        )


def write(request, page: Page, title: str, body: str):
    """A new title and text; a new title gives the page a new address."""
    page.title, page.body = title, body
    page.save()


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


def delete(request, page: Page):
    """Delete a page that has no pages under it; its history stays."""
    if page.children.exists():
        raise ValidationError(_('Move or delete the pages under this page first.'))
    page.delete()
