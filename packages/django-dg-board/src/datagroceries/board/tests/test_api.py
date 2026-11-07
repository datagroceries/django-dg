"""Tests for the board's REST API (datagroceries.board.api)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.test import APIClient

from datagroceries.board.activity import build_feed
from datagroceries.board.models import Column, Comment, Group, Relation, Ticket, Watcher
from datagroceries.board.tests import member
from datagroceries.core.tests import TEST_AUTHENTICATION, addressed, issue

URL = '/dg/board/api/tickets/'


@override_settings(DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
class TicketApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = member(
            username='anna',
            email='anna@example.com',
            first_name='Anna',
            last_name='Tester',
        )
        cls.bob = member(username='bob', email='bob@example.com', first_name='Bob')
        cls.group = Group.objects.create(name='Platform', slug='platform')
        cls.icebox = Column.objects.create(group=cls.group, name='Icebox', category=Column.Category.TODO, position=0)
        cls.todo = Column.objects.create(group=cls.group, name='To do', category=Column.Category.TODO, position=1)
        cls.doing = Column.objects.create(
            group=cls.group,
            name='Doing',
            category=Column.Category.IN_PROGRESS,
            position=2,
        )
        cls.done = Column.objects.create(group=cls.group, name='Done', category=Column.Category.DONE, position=3)
        cls.other = Group.objects.create(name='Data', slug='data')
        cls.other_doing = Column.objects.create(
            group=cls.other,
            name='Doing',
            category=Column.Category.IN_PROGRESS,
            position=0,
        )

    def setUp(self):
        key = issue(self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {key}')

    def make_ticket(self, title='A ticket', column=None, **fields):
        ticket = Ticket(title=title, creator=self.user, **fields)
        ticket.move_to(column or self.todo)
        return ticket

    def get(self, path, params=None):
        return self.client.get(f'{URL}{path}', params)

    def send(self, method, path, data):
        return getattr(self.client, method)(f'{URL}{path}', data, format='json')


class AccessTests(TicketApiTestCase):
    """Whatever lets a request in (datagroceries.core.authentication); the personal tokens' own rules are tested
    with them, in django-dg-connect."""

    def test_a_valid_token_gets_in(self):
        response = self.get('groups/')

        self.assertEqual(response.status_code, 200)
        [platform] = [group for group in response.json() if group['slug'] == 'platform']
        columns = [column['name'] for column in platform['columns']]
        self.assertEqual(columns, ['Icebox', 'To do', 'Doing', 'Done'])

    def test_without_a_token_nobody_gets_in(self):
        self.client.credentials()

        self.assertEqual(self.get('groups/').status_code, 401)

    def test_deactivating_the_user_ends_their_tokens(self):
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        self.assertEqual(self.get('groups/').status_code, 401)

    def test_a_token_for_another_scope_is_refused(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.user, scopes=["elsewhere"])}')

        self.assertEqual(self.get('groups/').status_code, 403)

    def test_a_token_of_someone_who_may_not_use_the_board_is_refused(self):
        self.user.user_permissions.clear()

        self.assertEqual(self.get('groups/').status_code, 403)

    def test_a_logged_in_session_does_not_open_the_api(self):
        self.client.credentials()
        self.client.force_login(self.user)

        self.assertIn(self.get('groups/').status_code, (401, 403))

    def test_a_token_does_not_open_the_pages(self):
        response = self.client.get('/dg/board/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])


class ReadTests(TicketApiTestCase):
    def test_a_ticket_reads_with_its_comments_relations_and_watchers(self):
        ticket = self.make_ticket(description='Details')
        child = self.make_ticket('Child')
        Relation.objects.create(source=ticket, target=child, type=Relation.Type.PARENT_OF)
        comment = Comment.objects.create(ticket=ticket, author=self.bob, body='Question')
        Comment.objects.create(ticket=ticket, author=self.user, body='Answer', parent=comment)
        Watcher.objects.create(ticket=ticket, user=self.bob)

        data = self.get(f'{ticket.key}/').json()

        self.assertEqual(data['description'], 'Details')
        self.assertEqual(
            data['relations'],
            [{'kind': 'parent_of', 'key': child.key, 'title': 'Child', 'category': 'todo'}],
        )
        self.assertEqual(data['comments'][0]['replies'][0]['body'], 'Answer')
        self.assertEqual(data['watchers'], [{'name': 'Bob', 'handle': 'bob', 'email': 'bob@example.com'}])
        child_data = self.get(f'{child.key}/').json()
        self.assertEqual(child_data['relations'][0]['kind'], 'child_of')

    def test_an_unknown_key_is_a_404(self):
        self.assertEqual(self.get('EX-999999/').status_code, 404)

    def test_the_list_filters_on_every_parameter_given(self):
        mine = self.make_ticket('Fix the invoices', assignee=self.user)
        self.make_ticket('Fix the reports', assignee=self.bob)
        self.make_ticket('Done invoices', column=self.done, assignee=self.user)

        data = self.get('', {'q': 'fix', 'assignee': 'me', 'category': 'todo'}).json()

        self.assertEqual([ticket['key'] for ticket in data['results']], [mine.key])

    def test_a_key_in_the_search_finds_that_ticket(self):
        ticket = self.make_ticket('Something else')

        self.assertEqual([t['key'] for t in self.get('', {'q': ticket.key}).json()['results']], [ticket.key])


@mock.patch('datagroceries.core.notifications.send_notification')
class WriteTests(TicketApiTestCase):
    def test_a_ticket_is_created_in_the_intake_column_of_a_group(self, delay):
        parent = self.make_ticket('Parent')

        response = self.send(
            'post',
            '',
            {'title': 'New', 'group': 'platform', 'labels': ['api'], 'size': 'days', 'parent': parent.key},
        )

        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(title='New')
        self.assertEqual(ticket.column, self.todo)
        self.assertEqual(ticket.creator, self.user)
        self.assertEqual([label.name for label in ticket.labels.all()], ['api'])
        self.assertTrue(Relation.objects.filter(source=parent, target=ticket, type=Relation.Type.PARENT_OF).exists())
        self.assertTrue(Watcher.objects.filter(ticket=ticket, user=self.user).exists())

    def test_the_history_names_the_token(self, delay):
        response = self.send('post', '', {'title': 'New', 'column': 'Doing', 'group': 'platform'})
        ticket = Ticket.objects.get(title='New')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ticket.history.earliest().history_change_reason, 'via Claude Code')
        self.assertEqual(ticket.history.earliest().history_user, self.user)
        self.assertEqual(build_feed(ticket)[0].via, 'via Claude Code')

    def test_an_unknown_field_is_refused_by_name(self, delay):
        response = self.send('post', '', {'title': 'New', 'group': 'platform', 'priority': 'high'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'unknown_fields': ['priority']})

    def test_moving_to_done_tells_the_watchers(self, delay):
        ticket = self.make_ticket()
        Watcher.objects.create(ticket=ticket, user=self.bob)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.send('patch', f'{ticket.key}/', {'column': 'done'})

        self.assertEqual(response.json()['category'], 'done')
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)
        [call] = delay.enqueue.call_args_list
        self.assertEqual(addressed(call.args[0]), ['bob@example.com'])
        self.assertIn('http://', call.args[2])

    def test_a_column_of_another_group_needs_that_group(self, delay):
        ticket = self.make_ticket()

        self.assertEqual(self.send('patch', f'{ticket.key}/', {'column': str(self.other_doing.pk)}).status_code, 400)
        response = self.send('patch', f'{ticket.key}/', {'group': 'data', 'column': 'Doing'})

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.column, self.other_doing)

    def test_changing_the_group_picks_the_matching_column(self, delay):
        ticket = self.make_ticket(column=self.doing)

        self.send('patch', f'{ticket.key}/', {'group': 'data'})

        ticket.refresh_from_db()
        self.assertEqual(ticket.column, self.other_doing)

    def test_assigning_by_email_tells_the_assignee(self, delay):
        ticket = self.make_ticket()

        with self.captureOnCommitCallbacks(execute=True):
            self.send('patch', f'{ticket.key}/', {'assignee': 'BOB@example.com', 'title': 'Renamed'})

        ticket.refresh_from_db()
        self.assertEqual((ticket.assignee, ticket.title), (self.bob, 'Renamed'))
        self.assertEqual(addressed(delay.enqueue.call_args.args[0]), ['bob@example.com'])

    def test_an_unknown_assignee_changes_nothing(self, delay):
        ticket = self.make_ticket()

        response = self.send('patch', f'{ticket.key}/', {'title': 'Renamed', 'assignee': 'nobody@example.com'})

        self.assertEqual(response.status_code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.title, 'A ticket')

    def test_a_comment_and_a_reply_but_not_a_reply_to_a_reply(self, delay):
        ticket = self.make_ticket()

        comment = self.send('post', f'{ticket.key}/comments/', {'body': 'First'}).json()
        reply = self.send('post', f'{ticket.key}/comments/', {'body': 'Second', 'parent': comment['id']})
        nested = self.send('post', f'{ticket.key}/comments/', {'body': 'Third', 'parent': reply.json()['id']})

        self.assertEqual(reply.status_code, 201)
        self.assertEqual(nested.status_code, 400)
        self.assertIn('detail', nested.json())
        self.assertEqual(build_feed(ticket)[0].comment.via, 'via Claude Code')

    def test_only_its_author_edits_a_comment_and_only_a_new_mention_hears_of_it(self, delay):
        ticket = self.make_ticket()
        Watcher.objects.create(ticket=ticket, user=self.bob)
        mine = Comment.objects.create(ticket=ticket, author=self.user, body='First')
        theirs = Comment.objects.create(ticket=ticket, author=self.bob, body='Theirs')

        with self.captureOnCommitCallbacks(execute=True):
            edited = self.send('patch', f'{ticket.key}/comments/{mine.pk}/', {'body': 'First, @bob'})
        refused = self.send('patch', f'{ticket.key}/comments/{theirs.pk}/', {'body': 'Changed'})
        empty = self.send('patch', f'{ticket.key}/comments/{mine.pk}/', {'body': ' '})
        unknown = self.send('patch', f'{ticket.key}/comments/{theirs.pk + 1}/', {'body': 'Changed'})

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()['body'], 'First, @bob')
        self.assertEqual((refused.status_code, empty.status_code, unknown.status_code), (403, 400, 404))
        theirs.refresh_from_db()
        self.assertEqual(theirs.body, 'Theirs')
        # Bob watches anyway, but hears only that he is mentioned now, not that a comment changed.
        [call] = delay.enqueue.call_args_list
        self.assertEqual(addressed(call.args[0]), ['bob@example.com'])
        self.assertIn('mentioned you in', call.args[1])

    def test_relations_are_added_checked_and_removed(self, delay):
        ticket, other = self.make_ticket(), self.make_ticket('Other')

        added = self.send('post', f'{ticket.key}/relations/', {'kind': 'blocked_by', 'ticket': other.key})
        loop = self.send('post', f'{other.key}/relations/', {'kind': 'blocked_by', 'ticket': ticket.key})
        removed = self.send('delete', f'{ticket.key}/relations/', {'kind': 'blocked_by', 'ticket': other.key})

        self.assertEqual(added.json()['open_blockers'], [other.key])
        self.assertEqual(loop.status_code, 400)
        self.assertEqual(removed.json()['relations'], [])

    def test_relates_to_is_removed_from_either_side(self, delay):
        ticket, other = self.make_ticket(), self.make_ticket('Other')
        Relation.objects.create(source=other, target=ticket, type=Relation.Type.RELATES_TO)

        response = self.send('delete', f'{ticket.key}/relations/', {'kind': 'relates_to', 'ticket': other.key})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Relation.objects.exists())

    def test_blocking_takes_a_reason(self, delay):
        ticket = self.make_ticket()

        without = self.send('post', f'{ticket.key}/block/', {'blocked': True})
        blocked = self.send('post', f'{ticket.key}/block/', {'blocked': True, 'reason': 'Waiting for Elia'})
        again = self.send('post', f'{ticket.key}/block/', {'blocked': True, 'reason': 'Still'})

        self.assertEqual(without.status_code, 400)
        self.assertTrue(blocked.json()['is_blocked'])
        self.assertEqual(blocked.json()['comments'][0]['kind'], 'blocked')
        self.assertEqual(again.status_code, 400)

    def test_watching_can_be_switched_on_and_off(self, delay):
        ticket = self.make_ticket()

        self.send('post', f'{ticket.key}/watch/', {})
        self.assertTrue(Watcher.objects.filter(ticket=ticket, user=self.user).exists())
        self.send('delete', f'{ticket.key}/watch/', {})
        self.assertFalse(Watcher.objects.filter(ticket=ticket, user=self.user).exists())


class HostAuthentication(BaseAuthentication):
    """A host project's own way in, for the tests: the username in an X-Host-User header."""

    def authenticate(self, request):
        username = request.META.get('HTTP_X_HOST_USER')
        return (get_user_model().objects.get(username=username), 'a key of the host') if username else None


@override_settings(DG_AUTHENTICATION_CLASSES=['datagroceries.board.tests.test_api.HostAuthentication'])
class HostAuthenticationTests(TicketApiTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_HOST_USER='anna')

    def test_the_host_project_s_own_way_in_reaches_the_api(self):
        response = self.send('post', '', {'title': 'New', 'group': 'platform'})

        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(title='New')
        self.assertEqual(ticket.history.earliest().history_user, self.user)
        self.assertEqual(ticket.history.earliest().history_change_reason, 'via API')

    def test_only_for_members(self):
        get_user_model().objects.create_user(username='carl')
        self.client.credentials(HTTP_X_HOST_USER='carl')

        self.assertEqual(self.get('groups/').status_code, 403)

    def test_only_when_the_host_project_lists_it(self):
        with self.settings(DG_AUTHENTICATION_CLASSES=[]):
            self.assertEqual(self.get('groups/').status_code, 401)

    def test_the_mcp_endpoint_takes_it_too(self):
        message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
        response = self.client.post('/dg/mcp', message, format='json')

        self.assertIn('create_ticket', [tool['name'] for tool in response.json()['result']['tools']])
