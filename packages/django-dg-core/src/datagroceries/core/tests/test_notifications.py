"""Tests for telling people about a change, by email or through the project's own notifier
(datagroceries.core.notifications)."""

import smtplib
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from datagroceries.core import checks, notifications

SENT = []


class Recorder(notifications.Notifier):
    """A project's own notifier: it is handed the user and the message."""

    def send(self, user, message):
        SENT.append((user.username, message))


class NotifierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.ann = users.create_user('ann', email='ann@example.com')
        cls.bob = users.create_user('bob', email='bob@example.com')
        cls.nobody = users.create_user('nobody')

    def setUp(self):
        SENT.clear()

    def tell(self, *users):
        with self.captureOnCommitCallbacks(execute=True):
            notifications.notify(users, lambda: 'Ann commented on T-1', 'https://example.com/T-1', 'Done!')

    def test_an_email_by_default(self):
        self.tell(self.ann)

        [message] = mail.outbox
        self.assertEqual(
            (message.subject, message.to, message.body),
            ('Ann commented on T-1', ['ann@example.com'], 'Done!\n\nhttps://example.com/T-1'),
        )

    def test_someone_without_an_email_address_hears_nothing_by_default(self):
        self.tell(self.nobody)

        self.assertEqual(mail.outbox, [])

    def test_someone_inactive_is_not_told(self):
        self.bob.is_active = False

        self.tell(self.bob)

        self.assertEqual(mail.outbox, [])

    @override_settings(DG_NOTIFIER=f'{__name__}.Recorder')
    def test_the_projects_notifier_gets_the_user_and_the_message(self):
        self.tell(self.ann, self.nobody)

        self.assertEqual(
            sorted(SENT),
            [
                ('ann', notifications.Message('Ann commented on T-1', 'https://example.com/T-1', 'Done!')),
                ('nobody', notifications.Message('Ann commented on T-1', 'https://example.com/T-1', 'Done!')),
            ],
        )
        self.assertEqual(mail.outbox, [])

    def test_someone_who_cannot_be_reached_is_logged_and_the_others_still_hear(self):
        def refuse_bob(subject, body, sender, to):
            if to == ['bob@example.com']:
                raise smtplib.SMTPRecipientsRefused({})
            mail.outbox.append(to)

        with (
            mock.patch('datagroceries.core.notifications.send_mail', side_effect=refuse_bob),
            self.assertLogs('datagroceries.core.notifications', 'ERROR') as logged,
        ):
            self.tell(self.bob, self.ann)

        self.assertIn('bob', logged.output[0])
        self.assertEqual(mail.outbox, [['ann@example.com']])


class SettingTests(SimpleTestCase):
    def ids(self) -> list[str]:
        return [message.id for message in checks.check_notifier(None)]

    def test_email_needs_no_setting(self):
        self.assertEqual(self.ids(), [])

    @override_settings(DG_NOTIFIER='myproject.notifications.Pigeon')
    def test_a_notifier_that_cannot_be_imported_is_refused(self):
        self.assertEqual(self.ids(), ['dg.E003'])
