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
    if parent == page.parent:
        return
    with transaction.atomic():
        page.parent = parent
        page.position = _last_position(parent)
        page.save()


def delete(request, page: Page):
    """Delete a page that has no pages under it; its history stays."""
    if page.children.exists():
        raise ValidationError(_('Move or delete the pages under this page first.'))
    page.delete()
