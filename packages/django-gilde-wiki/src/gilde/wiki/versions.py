"""A page's versions, its history records, as the pages and the API show them: who made each, through
which agent, and what it changed, in words."""

from django.utils import formats, timezone
from django.utils.translation import gettext as _

from gilde.core import people
from gilde.wiki.models import Page


def changed_by(page: Page, record):
    """Who made the change `record` holds. A page made outside a request, as by a script, has no one in
    its first record, but has its creator."""
    if record is None:
        return None
    return record.history_user or (page.creator if record.history_type == '+' else None)


def name(user) -> str:
    return people.name(user) if user else _('Someone')


def via(record) -> str:
    """The history keeps "via Claude Code on my laptop" in English; it shows in the reader's language."""
    reason = (record.history_change_reason or '') if record else ''
    return _('via %(name)s') % {'name': reason.removeprefix('via ')} if reason.startswith('via ') else ''


def when(moment) -> str:
    return formats.date_format(timezone.localtime(moment), 'SHORT_DATETIME_FORMAT')


def _changes(record, previous, earlier: dict, parents: dict) -> list[str]:
    """What `record` changed since `previous`, the version before it, in words."""
    if previous is None:
        return [_('Created')]
    if record.restored_from:
        restored = earlier.get(record.restored_from)
        return [_('Brought back the version of %(when)s') % {'when': when(restored.history_date) if restored else '?'}]
    changes = []
    if record.title != previous.title:
        changes.append(_('Renamed to “%(title)s”') % {'title': record.title})
    if record.body != previous.body:
        changes.append(_('Text changed'))
    if record.parent_id != previous.parent_id:
        parent = parents.get(record.parent_id)
        changes.append(_('Moved under “%(title)s”') % {'title': parent.title} if parent else _('Moved to the top'))
    return changes


def of(page: Page) -> list[dict]:
    """Every version of the page, newest first: its `record`, the one before it (`previous`), who made it
    (`by`, a user, and `name`), `via`, and its `changes`."""
    records = list(page.history.select_related('history_user'))
    earlier = {record.history_id: record for record in records}
    parents = Page.objects.in_bulk({record.parent_id for record in records if record.parent_id})
    return [
        {
            'record': record,
            'previous': previous,
            'by': changed_by(page, record),
            'name': name(changed_by(page, record)),
            'via': via(record),
            'changes': _changes(record, previous, earlier, parents),
        }
        for record, previous in zip(records, [*records[1:], None], strict=True)
    ]
