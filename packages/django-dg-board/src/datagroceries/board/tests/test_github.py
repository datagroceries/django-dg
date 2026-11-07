"""Tests for linking code to tickets (tickets/github.py): commits, branches and pull requests, through the
webhook and the backfill, and what shows."""

import datetime
import hashlib
import hmac
import json
from unittest import mock

import requests
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from datagroceries.board import github
from datagroceries.board.models import CodeReference, Column, Group, Ticket
from datagroceries.board.tests import member
from datagroceries.core.tests import TEST_AUTHENTICATION, issue

SECRET = 'webhook-secret'
WRONG_SECRET = 'guessed'
TOKEN = 'token'
REPOSITORY = 'example/project'
WHEN = datetime.datetime(2026, 9, 24, 13, 0, tzinfo=datetime.UTC)


def pull_request(number, title, *, branch='feature', state='open', merged=False):
    return {
        'number': number,
        'title': title,
        'html_url': f'https://github.com/{REPOSITORY}/pull/{number}',
        'user': {'login': 'anna'},
        'state': state,
        'merged_at': '2026-09-24T15:00:00Z' if merged else None,
        'created_at': '2026-09-24T13:00:00Z',
        'head': {'ref': branch},
    }


def commit(sha, message):
    return {
        'sha': sha,
        'message': message,
        'url': f'https://github.com/{REPOSITORY}/commit/{sha}',
        'author': 'Anna',
        'committed_at': WHEN,
    }


class GithubTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = member(username='anna', email='anna@example.com')
        group = Group.objects.create(name='Platform', slug='platform')
        column = Column.objects.create(group=group, name='To do', category=Column.Category.TODO, position=0)
        cls.ticket = Ticket.objects.create(title='Invoices', creator=cls.user, column=column)
        cls.other = Ticket.objects.create(title='Other', creator=cls.user, column=column)


class RecordCommitsTests(GithubTestCase):
    def test_a_commit_is_linked_to_every_ticket_it_names_once(self):
        named = commit(
            'a' * 40, f'{self.ticket.key} Fix the invoice\n\nAlso {self.other.key}, and EX-999999 that is no ticket'
        )

        created = github.record_commits([named, commit('b' * 40, 'Nothing to link')])
        again = github.record_commits([named])

        self.assertEqual((created, again), (2, 0))
        reference = self.ticket.code_references.get()
        self.assertEqual((reference.title, reference.author), (f'{self.ticket.key} Fix the invoice', 'Anna'))
        self.assertEqual(self.other.code_references.get().ref, 'a' * 40)


@override_settings(DG_BOARD_GITHUB_WEBHOOK_SECRET=SECRET, DG_BOARD_GITHUB_REPOSITORY=REPOSITORY)
class WebhookTests(GithubTestCase):
    def deliver(self, payload, event='push', secret=SECRET):
        body = json.dumps(payload).encode()
        signature = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse('dg_board:github_webhook'),
            body,
            content_type='application/json',
            headers={'X-Hub-Signature-256': signature, 'X-GitHub-Event': event},
        )

    def push(self, ref='refs/heads/main', repository=REPOSITORY):
        return {
            'ref': ref,
            'repository': {'full_name': repository, 'default_branch': 'main'},
            'commits': [
                {
                    'id': 'c' * 40,
                    'message': f'{self.ticket.key} Fix it',
                    'url': f'https://github.com/{REPOSITORY}/commit/{"c" * 40}',
                    'timestamp': '2026-09-24T15:53:00+02:00',
                    'author': {'name': 'Anna Tester'},
                },
            ],
        }

    def test_a_push_to_main_links_its_commits_without_a_login(self):
        response = self.deliver(self.push())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'recorded': 1})
        self.assertEqual(self.ticket.code_references.get().author, 'Anna Tester')

    def test_a_wrong_signature_is_refused(self):
        response = self.deliver(self.push(), secret=WRONG_SECRET)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(CodeReference.objects.exists())

    @override_settings(DG_BOARD_GITHUB_WEBHOOK_SECRET='')
    def test_without_a_secret_every_delivery_is_refused(self):
        response = self.deliver(self.push(), secret='')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(CodeReference.objects.exists())

    def test_another_branch_repository_or_event_links_nothing(self):
        self.deliver(self.push(ref='refs/heads/anna/t-1-invoices'))
        self.deliver(self.push(repository='someone/else'))
        ping = self.deliver({'zen': 'Keep it logically awesome.'}, event='ping')

        self.assertEqual(ping.json(), {'recorded': 0})
        self.assertFalse(CodeReference.objects.exists())


@override_settings(DG_BOARD_GITHUB_REPOSITORY=REPOSITORY)
class BranchAndPullRequestTests(GithubTestCase):
    def event(self, name, payload):
        return github.handle_event(name, {'repository': {'full_name': REPOSITORY}, **payload})

    def references(self, ticket):
        return list(ticket.code_references.values_list('kind', 'ref', 'state'))

    def test_a_branch_counts_by_its_name_in_any_case(self):
        name = f'anna/{self.ticket.key.lower()}-invoices'
        self.event('create', {'ref': name, 'ref_type': 'branch', 'sender': {'login': 'jasper'}})
        self.event('create', {'ref': f'v1-{self.ticket.pk}', 'ref_type': 'tag', 'sender': {'login': 'jasper'}})

        self.assertEqual(self.references(self.ticket), [('branch', name, '')])

    def test_a_pull_request_replaces_its_branch_and_follows_its_state(self):
        branch = f'anna/{self.ticket.key.lower()}'
        self.event('create', {'ref': branch, 'ref_type': 'branch', 'sender': {'login': 'anna'}})
        self.event('pull_request', {'action': 'opened', 'pull_request': pull_request(42, 'Invoices', branch=branch)})
        opened = self.references(self.ticket)
        merged = pull_request(42, 'Invoices', branch=branch, state='closed', merged=True)
        self.event('pull_request', {'action': 'closed', 'pull_request': merged})

        self.assertEqual(opened, [('pull_request', '42', 'open')])
        self.assertEqual(self.references(self.ticket), [('pull_request', '42', 'merged')])

    def test_a_key_taken_out_of_the_title_takes_its_link_away(self):
        self.event(
            'pull_request',
            {'action': 'opened', 'pull_request': pull_request(5, f'{self.ticket.key} and {self.other.key}')},
        )
        self.event('pull_request', {'action': 'edited', 'pull_request': pull_request(5, f'{self.other.key} only')})

        self.assertEqual(self.references(self.ticket), [])
        self.assertEqual(self.references(self.other), [('pull_request', '5', 'open')])

    def test_the_description_does_not_count(self):
        described = {**pull_request(6, 'No key here'), 'body': f'Unlike {self.ticket.key}'}
        self.event('pull_request', {'action': 'opened', 'pull_request': described})

        self.assertEqual(self.references(self.ticket), [])


@override_settings(DG_BOARD_GITHUB_TOKEN=TOKEN, DG_BOARD_GITHUB_REPOSITORY=REPOSITORY)
class BackfillTests(GithubTestCase):
    def test_the_history_of_main_is_read_page_by_page(self):
        page = [
            {
                'sha': 'd' * 40,
                'html_url': f'https://github.com/{REPOSITORY}/commit/{"d" * 40}',
                'commit': {
                    'message': f'{self.other.key} An old one',
                    'author': {'name': 'Bob', 'date': '2025-03-27T10:00:00Z'},
                },
            },
        ]
        pulls = [pull_request(7, f'{self.other.key} Also old', merged=True)]
        responses = [{'default_branch': 'main'}, page, [], pulls, []]
        with mock.patch('datagroceries.board.github.requests.get') as get:
            get.return_value.json.side_effect = responses
            call_command('backfill_github', stdout=mock.Mock())

        reference = self.other.code_references.get(kind='commit')
        self.assertEqual((reference.kind, reference.author, reference.happened_at.year), ('commit', 'Bob', 2025))
        self.assertEqual(get.call_args_list[1].kwargs['params']['sha'], 'main')
        self.assertEqual(
            self.other.code_references.get(kind='pull_request').state,
            'merged',
        )
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], f'Bearer {TOKEN}')

    def test_a_token_without_the_permission_gets_a_clear_message(self):
        refused = requests.Response()
        refused.status_code, refused.url = 403, 'https://api.github.com/repos/example/project/pulls'
        with (
            mock.patch('datagroceries.board.github._get', side_effect=requests.HTTPError(response=refused)),
            self.assertRaisesMessage(CommandError, 'needs read-only Contents, Pull requests and Metadata'),
        ):
            call_command('backfill_github', stdout=mock.Mock())

    @override_settings(DG_BOARD_GITHUB_TOKEN='')
    def test_without_a_token_the_backfill_stops(self):
        with self.assertRaisesMessage(CommandError, 'DG_BOARD_GITHUB_TOKEN is not set'):
            call_command('backfill_github', stdout=mock.Mock())


class DisplayTests(GithubTestCase):
    def test_the_ticket_page_and_the_api_show_the_linked_commits(self):
        github.record_commits([commit('e' * 40, f'{self.ticket.key} Show me')])
        self.client.force_login(self.user)

        page = self.client.get(self.ticket.get_absolute_url())

        self.assertContains(page, f'{self.ticket.key} Show me')
        self.assertContains(page, f'https://github.com/{REPOSITORY}/commit/{"e" * 40}')
        self.assertContains(page, f'<code class="tk-code-sha">{"e" * 7}</code>')
        self.assertContains(page, '<span class="text-truncate">Anna</span>')
        with self.settings(DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION):
            data = self.client.get(
                f'/dg/board/api/tickets/{self.ticket.key}/',
                headers={'Authorization': f'Bearer {issue(self.user)}'},
            ).json()
        self.assertEqual([(item['kind'], item['ref']) for item in data['code']], [('commit', 'e' * 40)])
