"""Tests for notifications by email and Slack, with one as the other's fallback (datagroceries.core.notifications)."""

import smtplib
from unittest import mock

import requests
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from datagroceries.core import checks, notifications

IN_SLACK = {'ann@example.com': 'U1'}  # Bob is not in the workspace


def slack_api(url, data, headers, timeout):
    """Slack's Web API, as far as the notifications use it."""
    response = mock.Mock()
    response.raise_for_status.return_value = None
    if url.endswith('users.lookupByEmail'):
        found = IN_SLACK.get(data['email'])
        response.json.return_value = (
            {'ok': True, 'user': {'id': found}} if found else {'ok': False, 'error': 'users_not_found'}
        )
    else:
        response.json.return_value = {'ok': True}
    return response


def send(*emails):
    notifications.send_notification.call(list(emails), 'Ann commented on T-1', 'https://example.com/T-1', 'Done!')


@override_settings(DG_SLACK_BOT_TOKEN='xoxb-test')
@mock.patch('datagroceries.core.notifications.requests.post', side_effect=slack_api)
class ChannelTests(SimpleTestCase):
    def slack_messages(self, post) -> list[str]:
        return [call.kwargs['data']['channel'] for call in post.call_args_list if call.args[0].endswith('postMessage')]

    def test_email_by_default(self, post):
        send('ann@example.com')

        [message] = mail.outbox
        self.assertEqual(
            (message.subject, message.to, message.body),
            ('Ann commented on T-1', ['ann@example.com'], 'Done!\n\nhttps://example.com/T-1'),
        )
        post.assert_not_called()

    @override_settings(DG_NOTIFICATIONS='slack')
    def test_slack_alone_may_be_given_as_a_string(self, post):
        send('ann@example.com')

        self.assertEqual(self.slack_messages(post), ['U1'])
        self.assertEqual(mail.outbox, [])

    @override_settings(DG_NOTIFICATIONS=['slack', 'email'])
    def test_whoever_slack_cannot_reach_gets_an_email(self, post):
        send('ann@example.com', 'bob@example.com')

        self.assertEqual(self.slack_messages(post), ['U1'])
        self.assertEqual([message.to for message in mail.outbox], [['bob@example.com']])

    @override_settings(DG_NOTIFICATIONS=['slack', 'email'])
    def test_everyone_gets_an_email_while_slack_is_down(self, post):
        post.side_effect = requests.ConnectionError('Slack is down')

        send('ann@example.com', 'bob@example.com')

        self.assertEqual(len(mail.outbox), 2)

    @override_settings(DG_NOTIFICATIONS=['email', 'slack'])
    def test_slack_takes_over_when_email_fails(self, post):
        with mock.patch('datagroceries.core.notifications.send_mail', side_effect=smtplib.SMTPException('refused')):
            send('ann@example.com')

        self.assertEqual(self.slack_messages(post), ['U1'])

    @override_settings(DG_NOTIFICATIONS=['slack'])
    def test_someone_no_channel_reaches_is_logged_and_the_others_still_hear(self, post):
        with self.assertLogs('datagroceries.core.notifications', 'ERROR') as logged:
            send('bob@example.com', 'ann@example.com')

        self.assertIn('bob@example.com', logged.output[0])
        self.assertEqual(self.slack_messages(post), ['U1'])


class SettingTests(SimpleTestCase):
    def ids(self) -> list[str]:
        return [message.id for message in checks.check_notifications(None)]

    @override_settings(DG_NOTIFICATIONS=['pigeon'])
    def test_an_unknown_channel_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            notifications.channels()
        self.assertEqual(self.ids(), ['dg.E003'])

    @override_settings(DG_NOTIFICATIONS=['slack', 'email'], DG_SLACK_BOT_TOKEN='')
    def test_slack_needs_its_token(self):
        self.assertEqual(self.ids(), ['dg.E004'])

    @override_settings(DG_NOTIFICATIONS=['slack', 'email'], DG_SLACK_BOT_TOKEN='xoxb-test')
    def test_slack_with_its_token_passes(self):
        self.assertEqual(self.ids(), [])
