"""Messages about pages, to the people watching them and the people mentioned in them, through
datagroceries.core.notifications.

The operations call these after a change. Nobody is told about their own change, nor about a page they may not
read (datagroceries.wiki.access): they are not made to watch it either. Watchers hear about
comments, not about every save: a page is written in many small saves, which its history keeps. Each person
reads a message in their own language, so a message is a sentence still to translate.
"""

from django.utils.translation import gettext_lazy as _

from datagroceries.core import mentions, notifications, people
from datagroceries.core.notifications import Message
from datagroceries.wiki import access
from datagroceries.wiki.conf import SCOPE
from datagroceries.wiki.models import Page, Watcher


def watch(page: Page, *users):
    for user in users:
        if user is not None:
            Watcher.objects.get_or_create(page=page, user=user)


def _url(request, page: Page, anchor: str = '') -> str:
    return request.build_absolute_uri(f'{page.get_absolute_url()}{anchor}')


def _watchers(page: Page, *excluded) -> list:
    excluded_ids = {user.pk for user in excluded}
    watching = [watcher.user for watcher in page.watchers.select_related('user') if watcher.user_id not in excluded_ids]
    return access.readers(page, watching)


def written(request, page: Page, before: str):
    """After the page's text changed from `before`: whoever wrote it watches it, and the people newly
    @-mentioned in it hear about it, and watch it too."""
    watch(page, request.user)
    before_ids = {user.pk for user in mentions.mentioned(SCOPE, before)}
    new = [user for user in mentions.mentioned(SCOPE, page.body) if user.pk not in before_ids]
    new = access.readers(page, new)
    watch(page, *new)
    summary = notifications.say(_('%(person)s mentioned you in %(page)s'), person=people.name(request.user), page=page)
    notifications.send(new, Message('mentioned', summary, _url(request, page), page, request.user))


def commented(request, comment, before: str | None = None):
    """Tell the people @-mentioned in the comment and, when it is new, everyone else watching the page.
    An edited comment, which said `before`, tells only the people it newly mentions."""
    page, author = comment.page, comment.author
    watch(page, author)
    before_ids = {user.pk for user in mentions.mentioned(SCOPE, before or '')}
    mentioned = [user for user in mentions.mentioned(SCOPE, comment.body) if user.pk not in before_ids]
    mentioned = access.readers(page, mentioned)
    watch(page, *mentioned)
    url = _url(request, page, f'#comment-{comment.pk}')
    names = {'person': people.name(author), 'page': page}
    about = {'about': page, 'actor': author, 'quote': notifications.snippet(comment.body)}
    summary = notifications.say(_('%(person)s mentioned you on %(page)s'), **names)
    notifications.send(mentioned, Message('mentioned', summary, url, **about))
    if before is None:
        summary = notifications.say(_('%(person)s commented on %(page)s'), **names)
        notifications.send(_watchers(page, *mentioned), Message('commented', summary, url, **about))
