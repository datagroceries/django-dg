"""Tests for what someone may do per group (datagroceries.board.access): a project that restricts it in its
`People.may`, on the pages, in the API and the MCP tools that run it, and in who hears about what."""

from unittest import mock

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from datagroceries.board.models import Column, Comment, Group, Relation, Ticket, Watcher
from datagroceries.board.tests import member
from datagroceries.core import history, people
from datagroceries.core.people import People
from datagroceries.core.templatetags.dg_core import render_markdown
from datagroceries.core.tests import TEST_AUTHENTICATION, addressed, issue

API = '/dg/board/api/tickets/'


class Restricted(People):
    """A project of its own rules: Anna may do everything; Bob may change Platform's tickets, only comment
    on Sales', and not see Secret at all, nor manage any group."""

    BOB = {'platform': 'write', 'sales': 'comment'}  # noqa: RUF012 - read only

    def may(self, user, right, group):
        if user.username == 'anna':
            return True
        granted = self.BOB.get(group.slug) if group else None
        return granted is not None and people.includes(granted, right)


@override_settings(DG_PEOPLE=f'{__name__}.Restricted', DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
class AccessTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anna = member(username='anna', email='anna@example.com', first_name='Anna')
        cls.bob = member(username='bob', email='bob@example.com', first_name='Bob')
        cls.columns = {}
        for slug in ('platform', 'sales', 'secret'):
            group = Group.objects.create(name=slug.capitalize(), slug=slug)
            cls.columns[slug] = Column.objects.create(group=group, name='To do', category=Column.Category.TODO)
        cls.platform = cls.make_ticket('Fix the login', 'platform')
        cls.sales = cls.make_ticket('Call the bank', 'sales')
        cls.secret = cls.make_ticket('Acquire a rival', 'secret')

    @classmethod
    def make_ticket(cls, title, slug):
        ticket = Ticket(title=title, creator=cls.anna)
        ticket.move_to(cls.columns[slug])
        return ticket

    def setUp(self):
        self.client.force_login(self.bob)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.bob)}')


class ReadTests(AccessTestCase):
    def test_the_board_shows_only_the_groups_one_may_read(self):
        page = self.client.get(reverse('dg_board:board'), {'group': 'all'})

        self.assertContains(page, 'Fix the login')
        self.assertContains(page, 'Call the bank')
        self.assertNotContains(page, 'Acquire a rival')
        self.assertNotContains(page, '?group=secret')

    def test_a_ticket_one_may_not_read_is_not_found_anywhere(self):
        self.assertEqual(self.client.get(self.secret.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse('dg_board:ticket_peek', args=[self.secret.key])).status_code, 404)
        found = self.client.get(reverse('dg_board:ticket_search'), {'q': 'a'}).json()['results']
        self.assertNotIn(self.secret.key, [result['key'] for result in found])
        self.assertEqual(self.api.get(f'{API}{self.secret.key}/').status_code, 404)
        listed = self.api.get(API).json()['results']
        self.assertEqual(sorted(ticket['key'] for ticket in listed), sorted([self.platform.key, self.sales.key]))
        groups = self.api.get(f'{API}groups/').json()
        self.assertEqual([group['slug'] for group in groups], ['platform', 'sales'])

    def test_a_relation_to_it_shows_as_a_ticket_one_cannot_see(self):
        Relation.objects.create(source=self.secret, target=self.platform, type=Relation.Type.BLOCKS)

        page = self.client.get(self.platform.get_absolute_url())

        self.assertContains(page, 'a ticket you cannot see')
        self.assertNotContains(page, 'Acquire a rival')
        self.assertNotContains(page, self.secret.key)
        detail = self.api.get(f'{API}{self.platform.key}/').json()
        self.assertEqual(detail['open_blockers'], [None])
        hidden = {'kind': 'blocked_by', 'key': None, 'title': 'A ticket you cannot see', 'category': 'todo'}
        self.assertEqual(detail['relations'], [hidden])

    def test_a_card_does_not_name_a_parent_one_cannot_see(self):
        Relation.objects.create(source=self.secret, target=self.platform, type=Relation.Type.PARENT_OF)

        page = self.client.get(reverse('dg_board:board'), {'group': 'platform'})

        self.assertContains(page, 'Fix the login')
        self.assertNotContains(page, 'Acquire a rival')

    def test_its_key_in_a_text_links_without_its_title(self):
        request = RequestFactory().get('/')
        request.user = self.bob
        with history.recording(request):
            html = render_markdown(f'See {self.secret.key} and {self.platform.key}.')

        self.assertNotIn('Acquire a rival', html)
        self.assertIn('title="Fix the login"', html)

    def test_its_attachments_are_not_found(self):
        attachment = self.secret.attachments.create(
            file='dg/secret.txt', name='secret.txt', size=1, content_type='text/plain', uploaded_by=self.anna
        )

        self.assertEqual(self.client.get(attachment.get_absolute_url()).status_code, 404)


class WriteTests(AccessTestCase):
    def test_who_may_only_comment_sees_no_controls_and_cannot_change_anything(self):
        page = self.client.get(self.sales.get_absolute_url())

        self.assertContains(page, 'name="action" value="comment"')
        for action in ('title', 'description', 'block', 'child', 'relation', 'delete'):
            self.assertNotContains(page, f'name="action" value="{action}"')
        self.assertNotContains(page, 'data-tk-property')
        refused = self.client.post(self.sales.get_absolute_url(), {'action': 'title', 'title': 'Mine now'})
        self.assertEqual(refused.status_code, 403)
        moved = self.client.post(
            reverse('dg_board:ticket_move', args=[self.sales.pk]), {'column': self.columns['sales'].pk}
        )
        self.assertEqual(moved.status_code, 403)

    def test_who_may_only_comment_may_comment(self):
        with mock.patch('datagroceries.core.notifications.send_notification'):
            self.client.post(self.sales.get_absolute_url(), {'action': 'comment', 'body': 'On it'})

        self.assertEqual(Comment.objects.get().body, 'On it')
        self.assertEqual(self.api.post(f'{API}{self.sales.key}/comments/', {'body': 'Me too'}).status_code, 201)

    def test_the_api_says_which_right_is_missing(self):
        response = self.api.patch(f'{API}{self.sales.key}/', {'title': 'Mine now'}, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'detail': 'You may not write in Sales.'})
        self.assertEqual(self.api.post(API, {'title': 'New', 'group': 'sales'}).status_code, 403)

    def test_a_ticket_cannot_move_to_a_group_one_may_not_write_in(self):
        response = self.client.post(
            reverse('dg_board:ticket_update', args=[self.platform.pk]),
            {'field': 'group', 'value': Group.objects.get(slug='sales').pk},
        )

        self.assertEqual(response.status_code, 403)
        self.platform.refresh_from_db()
        self.assertEqual(self.platform.column.group.slug, 'platform')

    def test_a_relation_to_a_ticket_one_cannot_see_is_refused_as_not_there(self):
        response = self.api.post(
            f'{API}{self.platform.key}/relations/', {'kind': 'relates_to', 'ticket': self.secret.key}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('No such ticket.', str(response.json()))

    def test_the_new_ticket_form_offers_only_groups_one_may_write_in(self):
        page = self.client.get(reverse('dg_board:ticket_create'))

        self.assertContains(page, 'Platform')
        self.assertNotContains(page, '>Sales<')
        self.assertNotContains(page, 'Secret')


class ManageTests(AccessTestCase):
    def test_only_who_may_manage_changes_groups(self):
        board = self.client.get(reverse('dg_board:board'), {'group': 'platform'})

        self.assertNotContains(board, reverse('dg_board:group_create'))
        self.assertNotContains(board, reverse('dg_board:group_edit', args=['platform']))
        self.assertEqual(self.client.get(reverse('dg_board:group_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('dg_board:group_edit', args=['platform'])).status_code, 403)
        self.assertEqual(self.client.post(reverse('dg_board:group_delete', args=['platform'])).status_code, 403)

    def test_who_may_manage_still_does(self):
        self.client.force_login(self.anna)

        self.assertEqual(self.client.get(reverse('dg_board:group_edit', args=['secret'])).status_code, 200)


@mock.patch('datagroceries.core.notifications.send_notification')
class PeopleTests(AccessTestCase):
    def test_who_may_no_longer_read_a_ticket_does_not_hear_about_it(self, task):
        Watcher.objects.create(ticket=self.secret, user=self.bob)
        self.client.force_login(self.anna)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.secret.get_absolute_url(), {'action': 'comment', 'body': 'Done'})

        self.assertEqual(task.enqueue.call_args_list, [])

    def test_who_may_not_read_a_ticket_is_not_mentioned_into_watching_it(self, task):
        self.client.force_login(self.anna)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.secret.get_absolute_url(), {'action': 'comment', 'body': '@bob, have a look'})

        self.assertEqual(task.enqueue.call_args_list, [])
        self.assertEqual(list(self.secret.watchers.values_list('user__username', flat=True)), ['anna'])

    def test_who_may_read_it_still_hears(self, task):
        self.client.force_login(self.anna)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.sales.get_absolute_url(), {'action': 'comment', 'body': '@bob, have a look'})

        [call] = task.enqueue.call_args_list
        self.assertEqual(addressed(call.args[0]), ['bob@example.com'])

    def test_a_ticket_is_assigned_only_to_who_may_read_it(self, task):
        anna = APIClient()
        anna.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.anna)}')

        refused = anna.patch(f'{API}{self.secret.key}/', {'assignee': 'bob'}, format='json')

        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json(), {'assignee': ['bob may not see Secret.']})
        self.assertEqual(anna.patch(f'{API}{self.sales.key}/', {'assignee': 'bob'}, format='json').status_code, 200)


class RightsTests(TestCase):
    def test_each_right_includes_the_ones_before_it(self):
        self.assertTrue(people.includes('write', 'comment'))
        self.assertFalse(people.includes('write', 'manage'))

    def test_an_unknown_right_is_a_mistake(self):
        with self.assertRaises(ValueError):
            people.may(None, 'delete', None)
