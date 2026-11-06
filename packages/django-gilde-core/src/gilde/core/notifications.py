"""Telling people about a change: by email, in a Slack direct message, or the one with the other as a
fallback.

`GILDE_NOTIFICATIONS` lists the channels in the order to try them, for each person apart: the first that
reaches them is used. `['email']` (the default) sends through Django's email settings; `['slack']` sends a
direct message from the bot whose token is `GILDE_SLACK_BOT_TOKEN`, to the Slack user with the same email
address; `['slack', 'email']` does that, and emails whoever Slack cannot reach: someone not in the
workspace, or anyone while Slack is down. One channel may also be given as a string.

A message goes out once the change is committed, as a task on Django's task backend (`TASKS`), which runs
it at once unless the host project sets up a worker. On Django 5.2 that takes the `django-tasks` backport;
without it, the message goes out in the request. Someone no channel reaches is logged, not raised, so the
others still hear about it.
"""

import logging
import smtplib

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import transaction

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


from gilde.core import people

logger = logging.getLogger(__name__)
SLACK_API = 'https://slack.com/api/'


class UnreachableError(Exception):
    """A channel cannot reach this person, now: the next channel is tried."""


def notify(users, summary: str, url: str, quote: str = ''):
    """Tell `users` that `summary` ("Ann commented on T-12 Fix the login"), with a link to `url` and
    the text it is about, if any, once the current transaction is committed."""
    emails = sorted({address for user in users if user.is_active and (address := people.email(user))})
    if emails:
        transaction.on_commit(lambda: send_notification.enqueue(emails, summary, url, quote))


def channels() -> list[str]:
    """The channels to try, in order (GILDE_NOTIFICATIONS)."""
    setting = getattr(settings, 'GILDE_NOTIFICATIONS', ['email'])
    found = [setting] if isinstance(setting, str) else list(setting)
    if not found or any(channel not in CHANNELS for channel in found):
        raise ImproperlyConfigured(f'GILDE_NOTIFICATIONS is {setting!r}; it lists "email" and "slack".')
    return found


@task
def send_notification(emails: list[str], summary: str, url: str, quote: str):
    order = channels()
    for email in emails:
        for channel in order:
            try:
                CHANNELS[channel](email, summary, url, quote)
                break
            except UnreachableError as reason:
                logger.info('Notification by %s did not reach %s: %s', channel, email, reason)
        else:
            logger.error('No notification channel reached %s about %r.', email, summary)


def _by_email(email: str, summary: str, url: str, quote: str):
    body = f'{quote}\n\n{url}' if quote else url
    try:
        send_mail(summary, body, None, [email])
    except (smtplib.SMTPException, OSError) as error:
        raise UnreachableError(error) from error


def _by_slack(email: str, summary: str, url: str, quote: str):
    text = f'<{url}|{_slack_escape(summary)}>'
    if quote:
        text += '\n' + '\n'.join(f'> {_slack_escape(line)}' for line in quote.splitlines())
    user = _slack('users.lookupByEmail', {'email': email})['user']
    _slack('chat.postMessage', {'channel': user['id'], 'text': text})


CHANNELS = {'email': _by_email, 'slack': _by_slack}


def _slack(method: str, data: dict) -> dict:
    """Call Slack's Web API. Slack being down, a refusal, or someone not in the workspace
    (`users_not_found`) all make the person unreachable this way."""
    try:
        response = requests.post(
            f'{SLACK_API}{method}',
            data=data,
            headers={'Authorization': f'Bearer {settings.GILDE_SLACK_BOT_TOKEN}'},
            timeout=10,
        )
        response.raise_for_status()
        answer = response.json()
    except (requests.RequestException, ValueError) as error:
        raise UnreachableError(f'Slack {method}: {error}') from error
    if not answer.get('ok'):
        raise UnreachableError(f'Slack {method}: {answer.get("error")}')
    return answer


def _slack_escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
