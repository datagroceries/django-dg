"""Tests for telling people about a change, by email or through the project's own notifier
(datagroceries.core.notifications)."""

import io
import json
import smtplib
import urllib.error
import urllib.parse
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, TestCase, override_settings

from datagroceries.core import checks, notifications
from datagroceries.core.people import People

SENT = []


class Recorder(notifications.Notifier):
    """A project's own notifier: it is handed the user and the message."""

    def send(self, user, message):
        SENT.append((user.username, message))


class DutchBob(People):
    def language(self, user):
        return 'nl' if user.username == 'bob' else None


class NotifierTestCase(TestCase):
    """Ann, Bob, someone without an email address, and Carl, who comments on a ticket."""

    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.ann = users.create_user('ann', email='ann@example.com')
        cls.bob = users.create_user('bob', email='bob@example.com')
        cls.nobody = users.create_user('nobody')
        cls.carl = users.create_user('carl', email='carl@example.com', first_name='Carl')
        # What a message is about: a ticket or a page in the apps, any model here.
        cls.ticket = Group.objects.create(name='T-1 Fix the login')

    def setUp(self):
        SENT.clear()

    def message(self, **fields):
        return notifications.Message(
            **{
                'kind': 'commented',
                'summary': lambda: 'Carl commented on T-1 Fix the login',
                'url': 'https://example.com/T-1#comment-3',
                'about': self.ticket,
                'actor': self.carl,
                'quote': 'Done!',
                **fields,
            }
        )

    def tell(self, *users, **fields):
        with self.captureOnCommitCallbacks(execute=True):
            notifications.notify(users, self.message(**fields))


class NotifierTests(NotifierTestCase):
    def test_an_email_by_default_with_what_happened_first_and_why_last(self):
        self.tell(self.ann)

        [email] = mail.outbox
        self.assertEqual((email.subject, email.to), ('T-1 Fix the login', ['ann@example.com']))
        self.assertEqual(
            email.body,
            'Carl commented on T-1 Fix the login\n\nDone!\n\nhttps://example.com/T-1#comment-3\n\n-- \n'
            'You get this because you watch T-1 Fix the login.\n'
            'Stop watching on its page: https://example.com/T-1\n',
        )
        [(html, kind)] = email.alternatives
        self.assertEqual(kind, 'text/html')
        self.assertIn('<blockquote', html)
        self.assertIn('href="https://example.com/T-1#comment-3"', html)

    def test_every_email_about_one_thing_is_in_one_thread(self):
        self.tell(self.ann)
        self.tell(self.ann, kind='done', summary=lambda: 'Carl moved T-1 Fix the login to Done', quote='')

        first, second = mail.outbox
        thread = f'<auth.group.{self.ticket.pk}@example.com>'
        for email in first, second:
            self.assertEqual((email.extra_headers['In-Reply-To'], email.extra_headers['References']), (thread, thread))
        self.assertEqual(first.subject, second.subject)
        self.assertNotEqual(first.message()['Message-ID'], second.message()['Message-ID'])

    @override_settings(DG_PEOPLE=f'{__name__}.DutchBob')
    def test_in_each_persons_language(self):
        self.tell(self.bob)

        [email] = mail.outbox
        self.assertIn('Je krijgt dit omdat je T-1 Fix the login volgt.', email.body)
        self.assertIn('<html lang="nl">', email.alternatives[0][0])

    def test_a_text_is_not_escaped_in_the_plain_email(self):
        self.ticket.name = 'T-1 Login & logout'
        self.ticket.save()

        self.tell(self.ann, quote='<b>bold</b> & "quoted"')

        [email] = mail.outbox
        self.assertEqual(email.subject, 'T-1 Login & logout')
        self.assertIn('<b>bold</b> & "quoted"', email.body)
        self.assertIn('&lt;b&gt;bold&lt;/b&gt; &amp;', email.alternatives[0][0])

    def test_someone_without_an_email_address_hears_nothing_by_default(self):
        self.tell(self.nobody)

        self.assertEqual(mail.outbox, [])

    def test_someone_inactive_is_not_told(self):
        self.bob.is_active = False

        self.tell(self.bob)

        self.assertEqual(mail.outbox, [])

    def test_the_actor_is_not_told_about_their_own_change(self):
        with self.captureOnCommitCallbacks(execute=True):
            notifications.send([self.ann, self.carl], self.message())

        self.assertEqual([email.to for email in mail.outbox], [['ann@example.com']])

    @override_settings(DG_NOTIFIER=f'{__name__}.Recorder')
    def test_the_projects_notifier_gets_the_user_and_the_whole_event(self):
        self.tell(self.ann, self.nobody)

        expected = notifications.Message(
            kind='commented',
            summary='Carl commented on T-1 Fix the login',
            url='https://example.com/T-1#comment-3',
            about=self.ticket,
            actor=self.carl,
            quote='Done!',
            subject='T-1 Fix the login',
        )
        self.assertEqual(sorted(SENT, key=lambda sent: sent[0]), [('ann', expected), ('nobody', expected)])
        self.assertEqual(mail.outbox, [])

    @override_settings(DG_NOTIFIER=f'{__name__}.Recorder')
    def test_what_was_deleted_since_is_still_named(self):
        with self.captureOnCommitCallbacks(execute=True):
            notifications.notify([self.ann], self.message())
            self.ticket.delete()

        [(_, message)] = SENT
        self.assertEqual((message.about, message.subject), (None, 'T-1 Fix the login'))
        self.assertEqual(notifications.Notifier().thread_headers(message), {})

    def test_someone_who_cannot_be_reached_is_logged_and_the_others_still_hear(self):
        def refuse_bob(email):
            if email.to == ['bob@example.com']:
                raise smtplib.SMTPRecipientsRefused({})
            mail.outbox.append(email)

        with (
            mock.patch.object(EmailMultiAlternatives, 'send', autospec=True, side_effect=refuse_bob),
            self.assertLogs('datagroceries.core.notifications', 'ERROR') as logged,
        ):
            self.tell(self.bob, self.ann)

        self.assertIn('bob', logged.output[0])
        self.assertEqual([email.to for email in mail.outbox], [['ann@example.com']])


class Slack:
    """Slack's Web API, as far as the notifier asks it: it knows Ann, and takes every message."""

    def __init__(self, known=None, error=None):
        self.known = {'ann@example.com': 'U-ANN'} if known is None else known
        self.error = error
        self.calls = []

    def __call__(self, request, timeout):
        method = request.full_url.rsplit('/', 1)[1]
        fields = dict(urllib.parse.parse_qsl(request.data.decode()))
        self.calls.append((method, fields, request.headers['Authorization']))
        if isinstance(self.error, Exception):
            raise self.error
        if self.error:
            answer = {'ok': False, 'error': self.error}
        elif method == 'users.lookupByEmail':
            found = self.known.get(fields['email'])
            answer = {'ok': True, 'user': {'id': found}} if found else {'ok': False, 'error': 'users_not_found'}
        else:
            answer = {'ok': True}
        return io.BytesIO(json.dumps(answer).encode())

    def posted(self) -> list[dict]:
        return [fields for method, fields, _auth in self.calls if method == 'chat.postMessage']


@override_settings(DG_SLACK_BOT_TOKEN='xoxb-test')
class SlackTests(NotifierTestCase):
    """With a bot token, a direct message in Slack to whom it knows, and an email to the others."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.slack = Slack()
        patcher = mock.patch('datagroceries.core.notifications.urllib.request.urlopen', self.slack)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_whom_slack_knows_gets_a_direct_message_instead_of_an_email(self):
        self.tell(self.ann, quote='Done!\n<b>Really</b> & truly')

        [posted] = self.slack.posted()
        self.assertEqual(posted['channel'], 'U-ANN')
        self.assertEqual(
            posted['text'],
            '<https://example.com/T-1#comment-3|Carl commented on T-1 Fix the login>\n>Done!\n'
            '>&lt;b&gt;Really&lt;/b&gt; &amp; truly',
        )
        self.assertEqual(self.slack.calls[0][2], 'Bearer xoxb-test')
        self.assertEqual(mail.outbox, [])

    def test_whom_slack_does_not_know_gets_the_email_and_is_not_looked_up_again_today(self):
        self.tell(self.bob)
        self.tell(self.bob)

        self.assertEqual([email.to for email in mail.outbox], [['bob@example.com'], ['bob@example.com']])
        self.assertEqual([method for method, _fields, _auth in self.slack.calls], ['users.lookupByEmail'])

    def test_when_slack_fails_the_email_goes_and_it_is_logged(self):
        for error in ('invalid_auth', urllib.error.URLError('down')):
            with self.subTest(error=error):
                mail.outbox.clear()
                cache.clear()
                self.slack.error = error
                with self.assertLogs('datagroceries.core.notifications', 'WARNING') as logged:
                    self.tell(self.ann)

                self.assertIn('an email instead', logged.output[0])
                self.assertEqual([email.to for email in mail.outbox], [['ann@example.com']])

    def test_without_an_email_address_slack_is_not_asked(self):
        self.tell(self.nobody)

        self.assertEqual(self.slack.calls, [])

    def test_the_projects_own_notifier_is_its_own_and_slack_is_not_asked(self):
        with self.settings(DG_NOTIFIER=f'{__name__}.Recorder'):
            self.tell(self.ann)

        self.assertEqual(self.slack.calls, [])


class SettingTests(SimpleTestCase):
    def ids(self) -> list[str]:
        return [message.id for message in checks.check_notifier(None)]

    def test_email_needs_no_setting(self):
        self.assertEqual(self.ids(), [])

    @override_settings(DG_NOTIFIER='myproject.notifications.Pigeon')
    def test_a_notifier_that_cannot_be_imported_is_refused(self):
        self.assertEqual(self.ids(), ['dg.E003'])

    @override_settings(DG_SLACK_BOT_TOKEN='xoxp-a-users-token')
    def test_a_slack_token_that_is_not_a_bots_is_warned_about(self):
        self.assertEqual(self.ids(), ['dg.W004'])

    @override_settings(DG_SLACK_BOT_TOKEN='xoxb-a-bots-token')
    def test_a_slack_bot_token_is_fine(self):
        self.assertEqual(self.ids(), [])
