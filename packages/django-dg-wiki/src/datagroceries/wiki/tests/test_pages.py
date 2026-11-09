from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from datagroceries.core import markdown
from datagroceries.core.tests import person
from datagroceries.wiki.forms import fingerprint
from datagroceries.wiki.models import FormerPath, Page
from datagroceries.wiki.tests import member, serving


class WikiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = member(username='anna', first_name='Anna', last_name='Tester')

    def setUp(self):
        self.client.force_login(self.user)

    def render(self, text, context=None):
        """`text` as the wiki shows it to the person signed in."""
        with serving(self.user):
            return markdown.render(text, context=context)

    def make_page(self, title, parent=None, body=''):
        return Page.objects.create(title=title, parent=parent, body=body, creator=self.user)


class TreeTests(WikiTestCase):
    def test_the_address_follows_the_tree(self):
        engineering = self.make_page('Engineering')
        deploying = self.make_page('Deploying to production', engineering)

        self.assertEqual(deploying.path, 'engineering/deploying-to-production')
        self.assertEqual(deploying.get_absolute_url(), '/dg/wiki/engineering/deploying-to-production/')
        self.assertEqual(deploying.ancestors(), [engineering])

    def test_pages_beside_each_other_with_the_same_title_get_their_own_address(self):
        first = self.make_page('Notes')
        second = self.make_page('Notes')
        under = self.make_page('Notes', first)

        self.assertEqual([first.path, second.path, under.path], ['notes', 'notes-2', 'notes/notes'])

    def test_a_title_without_letters_still_gets_an_address(self):
        self.assertEqual(self.make_page('???').path, 'page')

    def test_a_page_keeps_its_address_while_its_title_gives_the_same_one(self):
        self.make_page('Notes')
        second = self.make_page('Notes')
        Page.objects.get(path='notes').delete()

        second.title = 'Notes!'
        second.save()

        self.assertEqual(second.path, 'notes-2')

    def test_renaming_moves_the_pages_under_it_and_keeps_the_old_addresses(self):
        engineering = self.make_page('Engineering')
        deploying = self.make_page('Deploying', engineering)
        self.make_page('Rollback', deploying)

        engineering.title = 'Development'
        engineering.save()

        self.assertEqual(
            sorted(Page.objects.values_list('path', flat=True)),
            ['development', 'development/deploying', 'development/deploying/rollback'],
        )
        self.assertEqual(
            dict(FormerPath.objects.values_list('path', 'page__path')),
            {
                'engineering': 'development',
                'engineering/deploying': 'development/deploying',
                'engineering/deploying/rollback': 'development/deploying/rollback',
            },
        )

    def test_a_new_page_at_an_old_address_takes_it_over(self):
        old = self.make_page('Engineering')
        old.title = 'Development'
        old.save()

        new = self.make_page('Engineering')

        self.assertEqual(new.path, 'engineering')
        self.assertFalse(FormerPath.objects.filter(path='engineering').exists())

    def test_a_page_cannot_go_under_itself_or_a_page_under_it(self):
        top = self.make_page('Top')
        below = self.make_page('Below', top)

        for parent in (top, below):
            top.parent = parent
            with self.assertRaises(ValidationError):
                top.clean()

    def test_the_tree_comes_from_one_query(self):
        top = self.make_page('Top')
        self.make_page('Below', top)
        self.make_page('Beside')

        with self.assertNumQueries(1):
            nodes = Page.objects.tree()

        self.assertEqual([node.page.title for node in nodes], ['Beside', 'Top'])
        self.assertEqual([node.page.title for node in nodes[1].children], ['Below'])


class PageTests(WikiTestCase):
    def test_a_page_shows_its_text_its_place_and_who_wrote_it(self):
        top = self.make_page('Engineering')
        self.client.post(reverse('dg_wiki:page_create'), {'title': 'Deploying', 'parent': top.pk})
        deploying = Page.objects.get(title='Deploying')
        self.client.post(
            reverse('dg_wiki:page_edit', args=[deploying.path]),
            {'title': 'Deploying', 'body': 'Pull, **migrate**, restart.', 'original': fingerprint(deploying)},
        )

        page = self.client.get(deploying.get_absolute_url())

        self.assertContains(page, '<strong>migrate</strong>')
        self.assertContains(page, f'<a href="{top.get_absolute_url()}">Engineering</a>', html=True)
        self.assertContains(page, 'Last changed by Anna Tester')

    def test_a_long_page_has_a_table_of_contents(self):
        page = self.make_page('Deploying', body='## Before\n\ntext\n\n## During\n\n### Rollback\n\n## After')

        response = self.client.get(page.get_absolute_url())

        self.assertContains(response, '<h2 id="h-before">Before</h2>', html=True)
        self.assertContains(response, '<a href="#h-rollback">Rollback</a>', html=True)

    def test_a_short_page_has_none(self):
        page = self.make_page('Deploying', body='## Before\n\n## After')

        self.assertNotContains(self.client.get(page.get_absolute_url()), 'wk-contents')

    def test_a_new_page_starts_from_its_title_and_opens_in_the_editor(self):
        response = self.client.post(reverse('dg_wiki:page_create'), {'title': 'Onboarding'})

        page = Page.objects.get()
        self.assertRedirects(response, reverse('dg_wiki:page_edit', args=['onboarding']))
        self.assertEqual((page.creator, page.body), (self.user, ''))

    def test_a_save_is_refused_when_someone_else_saved_first(self):
        page = self.make_page('Deploying', body='Pull.')
        started_from = fingerprint(page)
        bob = member(username='bob', first_name='Bob', last_name='Smith')
        self.client.force_login(bob)
        self.client.post(
            reverse('dg_wiki:page_edit', args=[page.path]),
            {'title': 'Deploying', 'body': 'Pull and restart.', 'original': started_from},
        )
        self.client.force_login(self.user)
        url = reverse('dg_wiki:page_edit', args=[page.path])

        refused = self.client.post(url, {'title': 'Deploying', 'body': 'Pull, migrate.', 'original': started_from})

        self.assertContains(refused, 'Bob Smith saved this page while you were editing it.')
        self.assertContains(refused, 'Pull, migrate.')
        page.refresh_from_db()
        self.assertEqual(page.body, 'Pull and restart.')

        self.client.post(url, {'title': 'Deploying', 'body': 'Pull, migrate.', 'original': fingerprint(page)})

        page.refresh_from_db()
        self.assertEqual(page.body, 'Pull, migrate.')

    def test_an_old_address_leads_to_the_page(self):
        page = self.make_page('Engineering')
        self.client.post(
            reverse('dg_wiki:page_edit', args=[page.path]),
            {'title': 'Development', 'body': '', 'original': fingerprint(page)},
        )

        self.assertRedirects(self.client.get('/dg/wiki/engineering/'), '/dg/wiki/development/')

    def test_the_address_of_no_page_offers_to_start_it_there(self):
        top = self.make_page('Engineering')

        response = self.client.get('/dg/wiki/engineering/release-notes/')

        self.assertContains(response, 'No such page yet', status_code=404)
        self.assertContains(response, 'value="Release notes"', status_code=404)
        self.assertContains(
            response, f'<option value="{top.pk}" selected>Engineering</option>', html=True, status_code=404
        )

    def test_moving_a_page_takes_the_pages_under_it(self):
        engineering = self.make_page('Engineering')
        handbook = self.make_page('Handbook')
        deploying = self.make_page('Deploying', engineering)
        self.make_page('Rollback', deploying)

        response = self.client.post(reverse('dg_wiki:page_move', args=[deploying.path]), {'parent': handbook.pk})

        self.assertRedirects(response, '/dg/wiki/handbook/deploying/')
        self.assertTrue(Page.objects.filter(path='handbook/deploying/rollback').exists())

    def test_a_page_cannot_be_moved_under_a_page_under_it(self):
        top = self.make_page('Top')
        below = self.make_page('Below', top)

        response = self.client.get(reverse('dg_wiki:page_move', args=[top.path]))

        self.assertNotContains(response, f'value="{below.pk}"')
        self.assertNotContains(response, f'value="{top.pk}"')

    def test_a_page_with_pages_under_it_is_not_deleted(self):
        top = self.make_page('Top')
        self.make_page('Below', top)

        self.client.post(reverse('dg_wiki:page_delete', args=[top.path]))

        self.assertTrue(Page.objects.filter(pk=top.pk).exists())

    def test_deleting_a_page_keeps_its_history(self):
        page = self.make_page('Old notes', body='Forget this.')

        self.client.post(reverse('dg_wiki:page_delete', args=[page.path]))

        self.assertFalse(Page.objects.exists())
        self.assertEqual(Page.history.filter(title='Old notes').count(), 2)

    def test_the_tree_opens_down_to_the_page_shown(self):
        top = self.make_page('Engineering')
        below = self.make_page('Deploying', top)
        self.make_page('Rollback', below)
        self.make_page('Handbook', self.make_page('People'))

        response = self.client.get(below.get_absolute_url()).content.decode()

        self.assertEqual(response.count('<details open>'), 2)
        self.assertIn('aria-current="page">Deploying</a>', response)


class AccessTests(WikiTestCase):
    def test_only_people_who_may_use_the_wiki_get_in(self):
        page = self.make_page('Salaries')
        self.client.force_login(person(username='visitor'))

        self.assertEqual(self.client.get(page.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.get(reverse('dg_wiki:home')).status_code, 403)

    def test_someone_not_signed_in_is_sent_to_sign_in(self):
        self.client.logout()

        self.assertEqual(self.client.get(reverse('dg_wiki:home')).status_code, 302)


@override_settings(LANGUAGE_CODE='nl')
class DutchTests(WikiTestCase):
    def test_the_wiki_speaks_dutch(self):
        page = self.make_page('Werkwijze')

        response = self.client.get(page.get_absolute_url())

        self.assertContains(response, 'Nieuwe pagina hieronder')
        self.assertContains(response, 'Laatst gewijzigd door Anna Tester')
