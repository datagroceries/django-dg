"""Telling people about a change.

Who hears about what is the apps' to decide: the people watching a ticket or a page, those @-mentioned,
a new assignee, never whoever made the change. How it reaches them comes from one class, `Notifier`, which is
handed each person and a `Message`: what happened (`kind`), who did it, what it is about, and a sentence
saying so in the person's language. By default it is an email through Django's email settings, to the
address `People` gives, from templates a project overrides as any other (`dg_core/notifications/`). A host
project that reaches its people another way, such as in Slack or Teams, inside the project, in a daily
digest or not at all when someone said so, names a subclass in `DG_NOTIFIER`; docs/integrating.md shows
one for Slack.

A message goes out once the change is committed, as a task on Django's task backend (`TASKS`), which runs
it at once unless the host project sets up a worker. On Django 5.2 that takes the `django-tasks` backport;
without it, the message goes out in the request. Someone the notifier fails to reach is logged, not
raised, so the others still hear about it.
"""

import dataclasses
import functools
import logging
from collections import defaultdict
from urllib.parse import urlsplit

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.core.signals import setting_changed
from django.db import transaction
from django.dispatch import receiver
from django.template.loader import render_to_string
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
    """What a person is told about a change.

    - `kind`: what happened, the same in every language, so a notifier can choose by it. The board says
      `assigned`, `mentioned`, `commented`, `blocked`, `unblocked` and `done`; the wiki `mentioned` and
      `commented`.
    - `summary`: the same in a sentence, in the person's language ("Ann commented on T-12 Fix the login").
    - `url`: where to see it, such as the comment on the ticket's page.
    - `subject`: what it is about, as people know it ("T-12 Fix the login"), and `about`, that ticket or
      page itself, or None when it was deleted since.
    - `actor`: who made the change.
    - `quote`: the text it concerns, if any, such as the start of the comment.
    """

    kind: str
    summary: str
    url: str
    about: object = None
    actor: object = None
    quote: str = ''
    subject: str = ''


class Notifier:
    """The default way people hear about a change: an email. Subclass it to reach them another way, and
    name the subclass in `DG_NOTIFIER`."""

    def send(self, user, message: Message):
        """Tell `user` the `message`: by default an email to their address (`people.email`), and nothing
        when they have none. It is written in their language, from the templates
        `dg_core/notifications/email_subject.txt`, `email.txt` and `email.html`, and every message about
        one ticket or page is in one thread."""
        if not (address := people.email(user)):
            return
        context = {'user': user, 'message': message, 'about_url': message.url.split('#')[0]}
        with translation.override(people.language(user)):
            subject = ' '.join(render_to_string('dg_core/notifications/email_subject.txt', context).split())
            text = render_to_string('dg_core/notifications/email.txt', context)
            html = render_to_string('dg_core/notifications/email.html', context)
        email = EmailMultiAlternatives(subject, text, None, [address], headers=self.thread_headers(message))
        email.attach_alternative(html, 'text/html')
        email.send()

    def thread_headers(self, message: Message) -> dict:
        """Headers that put every email about the same ticket or page in one thread, in mail programs that
        go by them, as Apple Mail, Outlook and Thunderbird do; Gmail goes by the subject, which is the same
        too."""
        if message.about is None:
            return {}
        domain = urlsplit(message.url).hostname or 'localhost'
        thread = f'<{message.about._meta.label_lower}.{message.about.pk}@{domain}>'
        return {'In-Reply-To': thread, 'References': thread}


@functools.cache
def notifier() -> Notifier:  # cleared when the setting changes, as in tests
    path = getattr(settings, 'DG_NOTIFIER', None)
    return import_string(path)() if path else Notifier()


@receiver(setting_changed)
def _forget_notifier(setting, **kwargs):
    if setting == 'DG_NOTIFIER':
        notifier.cache_clear()


def notify(users, message: Message):
    """Tell `users` the `message`, once the current transaction is committed.

    Each person reads it in their own language (people.language): the message's `summary` is a function
    that says it in the active language (`say`), called once for each language among them. Its `subject`
    is `about`'s name, unless it says otherwise.
    """
    by_language = defaultdict(list)
    for user in users:
        if user.is_active:
            # As text, so that the task's arguments are JSON whatever the user model's key is.
            by_language[people.language(user)].append(str(user.pk))
    about, actor = message.about, message.actor
    event = {
        'kind': message.kind,
        'url': message.url,
        'subject': message.subject or str(about),
        'about': [about._meta.label_lower, str(about.pk)],
        'actor': str(actor.pk) if actor else None,
        'quote': message.quote,
    }
    for language, pks in by_language.items():
        with translation.override(language):
            said = {**event, 'summary': message.summary()}
        transaction.on_commit(functools.partial(send_notification.enqueue, pks, said))


def _find(model, pk):
    return model._default_manager.filter(pk=pk).first() if pk is not None else None


@task
def send_notification(pks: list[str], event: dict):
    """Tell the users with `pks` about `event`, a `Message` as JSON, with the keys of `about` and `actor`."""
    message = Message(
        **{
            **event,
            'about': _find(apps.get_model(event['about'][0]), event['about'][1]),
            'actor': _find(get_user_model(), event['actor']),
        }
    )
    for user in get_user_model()._default_manager.filter(pk__in=pks):
        try:
            notifier().send(user, message)
        except Exception:
            logger.exception('Notifying %s of %r failed.', user, message.summary)


SNIPPET_LENGTH = 300


def snippet(text: str) -> str:
    """The start of `text`, to quote in a notification."""
    text = text.strip()
    return text[:SNIPPET_LENGTH].rstrip() + '…' if len(text) > SNIPPET_LENGTH else text


def say(sentence, **names):
    """`sentence` with `names` filled in, in the language active when it is said: a message's summary for
    `send`."""
    return lambda: str(sentence) % names


def send(users, message: Message):
    """Tell `users`, but not the message's actor, who made the change, each in their own language."""
    notify([user for user in users if user != message.actor], message)
