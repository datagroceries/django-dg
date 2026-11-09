"""Tests for what someone may do per page (datagroceries.wiki.access): a project that restricts it in its
`People.may`, on the pages, in the API and the MCP tools that run it, and in who hears about what."""

import io
import zipfile
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from datagroceries.core import people
from datagroceries.core.people import People
from datagroceries.core.tests import TEST_AUTHENTICATION, addressed, issue
from datagroceries.wiki import search
from datagroceries.wiki.models import TOP, Comment, Page
from datagroceries.wiki.tests import member, serving
from datagroceries.wiki.tests import page as new_page
from datagroceries.wiki.tests.test_pages import WikiTestCase

API = '/dg/wiki/-/api/pages/'


class Restricted(People):
    """A project of its own rules, given to a page and the pages under it, the nearest one counting: Anna may
    do everything; Bob what `BOB` says, by page, with None for the top and '' for nothing at all."""

    BOB = {}  # noqa: RUF012 - filled in per test case
    asked = 0

    def may(self, user, right, where):
        Restricted.asked += 1
        if user.username == 'anna':
            return True
        granted = self.BOB.get(None)
        for page in reversed([*where.ancestors(), where] if where is not TOP else []):
            if page.pk in self.BOB:
                granted = self.BOB[page.pk]
                break
        return bool(granted) and people.includes(granted, right)


@override_settings(DG_PEOPLE=f'{__name__}.Restricted', DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
class AccessTestCase(WikiTestCase):
    """Bob may read the wiki, write in Engineering but not see its Acquisitions, only comment in Sales,
    and only read Legal."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bob = member(username='bob', email='bob@example.com', first_name='Bob')

        def make(title, parent=None, body=''):
            return new_page(title, cls.user, parent, body=body)

        cls.engineering = make('Engineering')
        cls.infra = make('Infra', cls.engineering, body='Servers. See [[acquisitions]].')
        cls.secret = make('Acquisitions', cls.engineering, body='Buy the rival. [[Infra]] scales.')
        cls.plan = make('Plan', cls.secret)
        cls.sales = make('Sales')
        cls.quarter = make('Q4', cls.sales)
        cls.legal = make('Legal')
        cls.rules = {
            None: 'read',
            cls.engineering.pk: 'write',
            cls.secret.pk: '',
            # Under a page he may not read, this counts for nothing.
            cls.plan.pk: 'write',
            cls.sales.pk: 'comment',
        }

    def setUp(self):
        super().setUp()
        Restricted.BOB = self.rules
        self.client.force_login(self.bob)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.bob, scopes=("wiki",))}')


class ReadTests(AccessTestCase):
    def test_the_tree_home_and_search_show_only_the_pages_one_may_read(self):
        home = self.client.get(reverse('dg_wiki:home'))
        found = self.client.get(reverse('dg_wiki:search'), {'q': 'a'})

        for page in (home, found):
            self.assertContains(page, 'Infra')
            self.assertNotContains(page, 'Acquisitions')
            self.assertNotContains(page, '>Plan<')
        listed = self.api.get(API).json()['results']
        self.assertEqual(
            [each['path'] for each in listed],
            ['engineering', 'engineering/infra', 'legal', 'sales', 'sales/q4'],
        )
        self.assertEqual(self.api.get(API, {'q': 'rival'}).json()['count'], 0)

    def test_a_page_one_may_not_read_is_not_found_nor_are_the_pages_under_it(self):
        for page in (self.secret, self.plan):
            self.assertEqual(self.client.get(page.get_absolute_url()).status_code, 404)
            self.assertEqual(self.client.get(reverse('dg_wiki:page_history', args=[page.path])).status_code, 404)
            self.assertEqual(self.api.get(f'{API}{page.path}/').status_code, 404)

    def test_its_old_address_does_not_lead_to_it(self):
        self.secret.title = 'Mergers'
        self.secret.save()

        self.assertEqual(self.client.get('/dg/wiki/engineering/acquisitions/').status_code, 404)

    def test_a_link_to_it_shows_by_the_name_written_and_leads_nowhere(self):
        page = self.client.get(self.infra.get_absolute_url())

        self.assertContains(page, '<span class="wk-hidden" title="A page you cannot see">acquisitions</span>')
        self.assertNotContains(page, 'engineering/acquisitions')

    def test_it_is_not_among_the_pages_that_link_to_one(self):
        self.assertNotContains(self.client.get(self.infra.get_absolute_url()), 'Pages that link here')
        self.assertEqual(self.api.get(f'{API}engineering/infra/').json()['linked_from'], [])

    def test_the_api_names_a_page_by_its_whole_address(self):
        self.make_page('Plan', self.sales)

        self.assertEqual(self.api.get(f'{API}sales/plan/').json()['path'], 'sales/plan')
        self.assertEqual(self.api.get(f'{API}plan/').status_code, 404)

    def test_its_files_are_not_found(self):
        attachment = self.secret.attachments.create(
            file='dg/secret.txt', name='secret.txt', size=1, content_type='text/plain', uploaded_by=self.user
        )

        self.assertEqual(self.client.get(attachment.get_absolute_url()).status_code, 404)

    def test_the_download_leaves_it_out(self):
        download = self.client.get(reverse('dg_wiki:wiki_export'))

        names = zipfile.ZipFile(io.BytesIO(download.content)).namelist()
        self.assertIn('engineering/infra.md', names)
        self.assertNotIn('engineering/acquisitions.md', names)
        self.assertNotIn('engineering/acquisitions/plan.md', names)

    def test_it_does_not_name_a_ticket_to_one(self):
        Page.objects.filter(pk__in=[self.secret.pk, self.legal.pk]).update(body='Waits for T-12.')

        with serving(self.bob):
            self.assertEqual([place.title for place in search.naming('T-12')], ['Legal'])

    def test_a_branch_one_may_not_read_is_not_asked_about(self):
        Restricted.asked = 0

        self.client.get(reverse('dg_wiki:home'))

        # Reading the top and the pages he may read, and Acquisitions, not Plan under it; writing those he may
        # read, to drag them; and writing at the top, for "New page".
        self.assertEqual(Restricted.asked, 1 + 6 + 5 + 1)


class WriteTests(AccessTestCase):
    def test_who_may_only_read_sees_no_controls_and_cannot_change_anything(self):
        page = self.client.get(self.legal.get_absolute_url())

        for control in ('page_edit', 'page_move', 'page_delete', 'page_attach', 'comment_create'):
            self.assertNotContains(page, reverse(f'dg_wiki:{control}', args=[self.legal.path]))
        self.assertEqual(self.client.get(reverse('dg_wiki:page_edit', args=[self.legal.path])).status_code, 403)
        refused = self.client.post(reverse('dg_wiki:comment_create', args=[self.legal.path]), {'body': 'Hm'})
        self.assertEqual(refused.status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_who_may_comment_comments_under_the_page_the_right_was_given_on(self):
        with mock.patch('datagroceries.core.notifications.send_notification'):
            self.client.post(reverse('dg_wiki:comment_create', args=[self.quarter.path]), {'body': 'On it'})

        self.assertEqual(Comment.objects.get().body, 'On it')
        self.assertEqual(self.api.post(f'{API}sales/q4/-/comments/', {'body': 'Me too'}).status_code, 201)
        refused = self.api.patch(f'{API}sales/q4/', {'body': 'Mine now'}, format='json')
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json(), {'detail': 'You may not write on sales/q4.'})

    def test_who_may_write_writes_and_starts_pages_under_it_but_not_at_the_top(self):
        self.assertEqual(self.api.patch(f'{API}engineering/infra/', {'body': 'More'}, format='json').status_code, 200)
        self.assertEqual(self.api.post(API, {'title': 'Runbook', 'parent': 'engineering'}).status_code, 201)
        refused = self.api.post(API, {'title': 'Mine'})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json(), {'detail': 'You may not write at the top of the wiki.'})

    def test_the_new_page_form_offers_only_places_one_may_write(self):
        form = self.client.get(reverse('dg_wiki:page_create')).context['form']

        self.assertEqual([label.strip() for _value, label in form.fields['parent'].choices], ['Engineering'])

    def test_a_page_moves_only_to_where_one_may_write(self):
        moved = self.api.patch(f'{API}engineering/infra/', {'parent': 'sales'}, format='json')

        self.assertEqual(moved.status_code, 403)
        self.infra.refresh_from_db()
        self.assertEqual(self.infra.path, 'engineering/infra')

    def test_a_page_cannot_be_dragged_out_of_a_place_one_may_only_read(self):
        dragged = self.client.post(
            reverse('dg_wiki:tree_arrange'), {'page': self.legal.pk, 'parent': self.engineering.pk}
        )

        self.assertEqual(dragged.status_code, 403)
        page = self.client.get(self.engineering.get_absolute_url())
        self.assertContains(page, f'data-page="{self.legal.pk}" draggable="false"')
        self.assertContains(page, f'data-page="{self.infra.pk}">')

    def test_a_page_a_link_names_is_started_only_where_one_may_write(self):
        refused = self.client.post('/dg/wiki/sales/contracts', {'title': 'Contracts'})

        self.assertContains(refused, 'You may not start a page here.', status_code=404)
        self.assertNotContains(refused, 'name="title"', status_code=404)
        self.assertFalse(Page.objects.filter(title='Contracts').exists())
        self.client.post('/dg/wiki/engineering/runbook', {'title': 'Runbook'})
        self.assertTrue(Page.objects.filter(path='engineering/runbook').exists())

    def test_under_a_page_one_may_not_read_an_address_is_not_found(self):
        missing = self.client.get('/dg/wiki/engineering/acquisitions/plan/budget/')

        self.assertEqual(missing.status_code, 404)
        self.assertNotContains(missing, 'Acquisitions', status_code=404)

    def test_the_start_page_is_changed_only_by_who_may_write_at_the_top(self):
        self.assertNotContains(self.client.get(reverse('dg_wiki:home')), 'Write a welcome')
        self.assertEqual(self.client.get(reverse('dg_wiki:home_edit')).status_code, 403)
        self.assertEqual(self.api.patch(f'{API.removesuffix("pages/")}start/', {'body': 'Mine'}).status_code, 403)

    def test_a_translation_goes_only_where_one_may_write(self):
        Page.objects.filter(pk__in=[self.legal.pk, self.infra.pk]).update(language='en')
        refused = self.api.post(f'{API}legal/-/translations/', {'language': 'nl', 'title': 'Juridisch'})

        self.assertEqual(refused.status_code, 403)
        made = self.api.post(f'{API}engineering/infra/-/translations/', {'language': 'nl', 'title': 'Infra NL'})
        self.assertEqual(made.status_code, 201)


@mock.patch('datagroceries.core.notifications.send_notification')
class PeopleTests(AccessTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_who_may_not_read_a_page_is_not_mentioned_into_watching_it(self, task):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('dg_wiki:comment_create', args=[self.plan.path]), {'body': '@bob, have a look'})

        self.assertEqual(task.enqueue.call_args_list, [])
        self.assertEqual(list(self.plan.watchers.values_list('user__username', flat=True)), ['anna'])

    def test_who_may_read_it_still_hears(self, task):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('dg_wiki:comment_create', args=[self.legal.path]), {'body': '@bob, have a look'})

        [call] = task.enqueue.call_args_list
        self.assertEqual(addressed(call.args[0]), ['bob@example.com'])

    def test_a_mention_of_someone_who_cannot_see_the_page_is_muted(self, task):
        Comment.objects.create(page=self.secret, author=self.user, body='@bob and @anna, have a look')

        page = self.client.get(self.secret.get_absolute_url())

        self.assertContains(page, '<span class="dg-mention dg-mention-unseen" title="Bob cannot see this">@bob</span>')
        self.assertContains(page, '<span class="dg-mention" title="Anna Tester">@anna</span>')
        self.assertContains(page, '{"handle": "bob", "name": "Bob", "unseen": true}')
