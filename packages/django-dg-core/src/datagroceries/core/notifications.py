"""Telling people about a change.

Who hears about what is the apps' to decide: the people watching a ticket or a page, those @-mentioned,
a new assignee, never whoever made the change. How it reaches them comes from one class, `Notifier`. By
default it is an email through Django's email settings, to the address `People` gives. A host project
that reaches its people another way, such as in Slack or Teams, inside the project, in a daily digest or
not at all when someone said so, names a subclass in `DG_NOTIFIER`; docs/integrating.md shows one for
Slack.

A message goes out once the change is committed, as a task on Django's task backend (`TASKS`), which runs
it at once unless the host project sets up a worker. On Django 5.2 that takes the `django-tasks` backport;
without it, the message goes out in the request. Someone the notifier fails to reach is logged, not
raised, so the others still hear about it.
"""

import dataclasses
import functools
import logging
from collections import defaultdict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.signals import setting_changed
from django.db import transaction
from django.dispatch import receiver
from django.utils import translation
from django.utils.module_loading import import_string

try:
    from django.tasks import task  # Django 6
except ImportError:
    try:
        from django_tasks import task  # the backport, on Django 5.2
    except ImportError:

        def task(function):
            """Without either, a notification goes out in the request, once the change is committed."""
            function.enqueue = function.call = function
            return function


from datagroceries.core import people

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Message:
    """What a person is told: `summary` in their language ("Ann commented on T-12 Fix the login"), a link
    to what it is about, and the text it concerns, if any."""

    summary: str
    url: str
    quote: str = ''


class Notifier:
    """The default way people hear about a change: an email. Subclass it to reach them another way, and
    name the subclass in `DG_NOTIFIER`."""

    def send(self, user, message: Message):
        """Tell `user` the `message`: by default an email to their address (`people.email`), and nothing
        when they have none."""
        if address := people.email(user):
            body = f'{message.quote}\n\n{message.url}' if message.quote else message.url
            send_mail(message.summary, body, None, [address])


@functools.cache
def notifier() -> Notifier:  # cleared when the setting changes, as in tests
    path = getattr(settings, 'DG_NOTIFIER', None)
    return import_string(path)() if path else Notifier()


@receiver(setting_changed)
def _forget_notifier(setting, **kwargs):
    if setting == 'DG_NOTIFIER':
        notifier.cache_clear()


def notify(users, summary, url: str, quote: str = ''):
    """Tell `users` that `summary`, with a link to `url` and the text it is about, if any, once the current
    transaction is committed.

    Each person reads it in their own language (people.language): `summary` is a function that says it
    in the active language, called once for each language among them.
    """
    by_language = defaultdict(list)
    for user in users:
        if user.is_active:
            # As text, so that the task's arguments are JSON whatever the user model's key is.
            by_language[people.language(user)].append(str(user.pk))
    for language, pks in by_language.items():
        with translation.override(language):
            text = summary()
        transaction.on_commit(functools.partial(send_notification.enqueue, pks, text, url, quote))


@task
def send_notification(pks: list[str], summary: str, url: str, quote: str):
    message = Message(summary, url, quote)
    for user in get_user_model()._default_manager.filter(pk__in=pks):
        try:
            notifier().send(user, message)
        except Exception:
            logger.exception('Notifying %s of %r failed.', user, summary)


SNIPPET_LENGTH = 300


def snippet(text: str) -> str:
    """The start of `text`, to quote in a notification."""
    text = text.strip()
    return text[:SNIPPET_LENGTH].rstrip() + '…' if len(text) > SNIPPET_LENGTH else text


def say(sentence, **names):
    """`sentence` with `names` filled in, in the language active when it is said: a summary for `send`."""
    return lambda: str(sentence) % names


def send(users, actor, summary, url: str, quote: str = ''):
    """Tell `users`, but not `actor`, who made the change, `summary` (from `say`), each in their own
    language."""
    notify([user for user in users if user.pk != actor.pk], summary, url, quote)
