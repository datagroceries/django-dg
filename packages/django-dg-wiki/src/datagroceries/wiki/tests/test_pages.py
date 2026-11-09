from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from datagroceries.core import markdown
from datagroceries.core.tests import person
from datagroceries.wiki.forms import fingerprint
from datagroceries.wiki.models import FormerPath, Page
from datagroceries.wiki.tests import member, page, serving


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

    def make_page(self, title, parent=None, body='', folder=False):
        return page(title, self.user, parent, body=body, folder=folder)


class TreeTests(WikiTestCase):
    def test_the_address_follows_the_tree(self):
        engineering = self.make_page('Engineering')
        deploying = self.make_page('Deploying to production', engineering)

        self.assertEqual(deploying.path, 'engineering/deploying-to-production')
        self.assertEqual(deploying.get_absolute_url(), '/dg/wiki/engineering/deploying-to-production')
        self.assertEqual(deploying.ancestors(), [engineering])

    def test_two_pages_of_a_name_cannot_be_beside_each_other_but_one_can_be_under_the_other(self):
        first = self.make_page('Notes')

        with self.assertRaises(ValidationError):
            self.make_page('notes!')
        under = self.make_page('Notes', first)

        self.assertEqual([first.path, under.path], ['notes', 'notes/notes'])

    def test_a_title_without_letters_still_gets_an_address(self):
        self.assertEqual(self.make_page('???').path, 'page')

    def test_a_page_keeps_its_address_while_its_title_gives_the_same_one(self):
        notes = self.make_page('Notes')

        notes.title = 'Notes!'
        notes.save()

        self.assertEqual(notes.path, 'notes')

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
        top = self.make_page('Engineering', folder=True)
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

        self.assertRedirects(self.client.get('/dg/wiki/engineering'), '/dg/wiki/development')

    def test_the_address_of_no_page_offers_to_start_it_there(self):
        top = self.make_page('Engineering', folder=True)

        response = self.client.get('/dg/wiki/engineering/release-notes')

        self.assertContains(response, 'No page at <code>/engineering/release-notes</code> yet', status_code=404)
        self.assertContains(response, 'type="hidden" name="title" value="Release notes"', status_code=404)
        self.assertContains(
            response,
            f'Start the page <strong>Release notes</strong>, in <a href="{top.get_absolute_url()}">Engineering</a>.',
            status_code=404,
        )
        self.assertNotContains(response, 'type="text"', status_code=404)
        self.assertNotContains(response, 'name="parent"', status_code=404)

    def test_a_page_started_at_an_address_goes_there_in_a_title_that_gives_it(self):
        top = self.make_page('Engineering', folder=True)

        response = self.client.post('/dg/wiki/engineering/release-notes', {'title': 'Release Notés'})

        self.assertRedirects(response, reverse('dg_wiki:page_edit', args=['engineering/release-notes']))
        started = Page.objects.get(path='engineering/release-notes')
        self.assertEqual((started.title, started.parent), ('Release Notés', top))

    def test_a_title_that_gives_another_address_is_refused(self):
        self.make_page('Engineering', folder=True)

        response = self.client.post('/dg/wiki/engineering/release-notes', {'title': 'What changed'})

        self.assertContains(response, 'the link would still lead nowhere', status_code=404)
        self.assertFalse(Page.objects.filter(title='What changed').exists())

    def test_the_folders_a_page_goes_in_are_made_with_it(self):
        response = self.client.get('/dg/wiki/engineering/international/belgium/voorbereiding?title=Voorbereiding')

        self.assertContains(
            response,
            'Engineering, International, Belgium are not there yet, and are made as folders too.',
            status_code=404,
        )
        self.client.post('/dg/wiki/engineering/international/belgium/voorbereiding', {'title': 'Voorbereiding'})
        self.assertEqual(
            list(Page.objects.order_by('path').values_list('path', 'title', 'folder')),
            [
                ('engineering', 'Engineering', True),
                ('engineering/international', 'International', True),
                ('engineering/international/belgium', 'Belgium', True),
                ('engineering/international/belgium/voorbereiding', 'Voorbereiding', False),
            ],
        )

    def test_a_page_at_the_top_says_so(self):
        response = self.client.get('/dg/wiki/also')

        self.assertContains(response, 'Start the page <strong>Also</strong>, at the top of the wiki.', status_code=404)

    def test_a_page_above_that_is_a_page_is_to_be_made_a_folder_first(self):
        self.make_page('Engineering')

        response = self.client.get('/dg/wiki/engineering/international/belgium')

        self.assertContains(response, 'which is a page, not a folder: make it a folder first', status_code=404)
        self.assertNotContains(response, 'name="title"', status_code=404)
        self.client.post('/dg/wiki/engineering/international/belgium', {'title': 'Belgium'})
        self.assertEqual(Page.objects.count(), 1)

    def test_an_address_no_title_gives_offers_no_page(self):
        response = self.client.get('/dg/wiki/Release notes/')

        self.assertContains(response, 'No title gives this address', status_code=404)
        self.assertNotContains(response, 'name="title"', status_code=404)

    def test_moving_a_page_takes_the_pages_under_it(self):
        engineering = self.make_page('Engineering')
        handbook = self.make_page('Handbook', folder=True)
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


class NameTests(WikiTestCase):
    """One name per folder, as in a file system."""

    def test_a_second_page_of_the_same_name_in_a_folder_is_refused(self):
        self.make_page('Notes')

        response = self.client.post(reverse('dg_wiki:page_create'), {'title': 'notes!'})

        self.assertContains(response, 'There is already a page called “Notes” here.')
        self.assertEqual(Page.objects.count(), 1)

    def test_a_page_is_not_renamed_or_moved_onto_another_s_name(self):
        engineering = self.make_page('Engineering', folder=True)
        self.make_page('Notes', engineering)
        other = self.make_page('Other')
        notes = self.make_page('Notes')

        renamed = self.client.post(
            reverse('dg_wiki:page_edit', args=[other.path]),
            {'title': 'Notes', 'body': '', 'language': '', 'original': fingerprint(other)},
        )
        moved = self.client.post(reverse('dg_wiki:page_move', args=[notes.path]), {'parent': engineering.pk})

        self.assertContains(renamed, 'There is already a page called “Notes” here.')
        self.assertContains(moved, 'There is already a page called “Notes” here.')
        self.assertEqual(Page.objects.filter(parent=engineering).count(), 1)


class FolderTests(WikiTestCase):
    """A page of its own, or a folder of pages, whose text is their index."""

    def test_a_folder_s_address_ends_in_a_slash_and_a_page_s_does_not(self):
        engineering = self.make_page('Engineering', folder=True)
        deploying = self.make_page('Deploying', engineering)

        self.assertEqual(
            (engineering.get_absolute_url(), deploying.get_absolute_url()),
            ('/dg/wiki/engineering/', '/dg/wiki/engineering/deploying'),
        )
        self.assertRedirects(self.client.get('/dg/wiki/engineering'), '/dg/wiki/engineering/')
        self.assertRedirects(self.client.get('/dg/wiki/engineering/deploying/'), '/dg/wiki/engineering/deploying')

    def test_a_page_goes_only_in_a_folder(self):
        platform = self.make_page('Platform')

        response = self.client.post(reverse('dg_wiki:page_create'), {'title': 'Testing', 'parent': platform.pk})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Page.objects.filter(title='Testing').exists())
        self.assertContains(
            self.client.get('/dg/wiki/platform/testing'), 'which is a page, not a folder', status_code=404
        )

    def test_a_page_made_a_folder_keeps_its_address_and_its_links_name_what_they_named(self):
        engineering = self.make_page('Engineering', folder=True)
        self.make_page('Algorithms', engineering)
        platform = self.make_page(
            'Platform',
            engineering,
            body='See [[Algorithms]], [[../Sales]], [[/Engineering/Algorithms|it]] and [[New]].',
        )

        response = self.client.post(reverse('dg_wiki:page_folder', args=[platform.path]), {'folder': 'yes'})

        platform.refresh_from_db()
        self.assertRedirects(response, '/dg/wiki/engineering/platform/')
        self.assertTrue(platform.folder)
        self.assertEqual(
            platform.body, 'See [[../Algorithms]], [[../../Sales]], [[/Engineering/Algorithms|it]] and [[../New]].'
        )
        history = self.client.get(reverse('dg_wiki:page_history', args=[platform.path]))
        self.assertContains(history, 'Made a folder')

    def test_a_folder_with_pages_in_it_stays_one(self):
        engineering = self.make_page('Engineering', folder=True)
        self.make_page('Platform', engineering)

        self.client.post(reverse('dg_wiki:page_folder', args=[engineering.path]), {'folder': 'no'})

        engineering.refresh_from_db()
        self.assertTrue(engineering.folder)
        self.client.post(reverse('dg_wiki:page_folder', args=[engineering.path]), {'folder': 'yes'})

    def test_an_empty_folder_opens_in_the_tree_and_says_so(self):
        self.make_page('Engineering', folder=True)

        response = self.client.get(reverse('dg_wiki:home'))

        self.assertContains(response, '<li class="wk-tree-empty">Nothing in it yet</li>', html=True)

    def test_the_editor_says_where_its_links_start(self):
        engineering = self.make_page('Engineering', folder=True)
        deploying = self.make_page('Deploying', engineering)

        folder = self.client.get(reverse('dg_wiki:page_edit', args=[engineering.path]))
        page = self.client.get(reverse('dg_wiki:page_edit', args=[deploying.path]))

        self.assertContains(folder, '<strong>Engineering</strong> is a folder: links written in it start in it.')
        self.assertContains(folder, '<code>[[Platform]]</code> is <code>/engineering/platform</code>')
        self.assertContains(page, 'is a page in the folder Engineering: links written in it start in Engineering.')
        self.assertContains(page, '<code>[[Platform]]</code> is <code>/engineering/platform</code>')
        self.assertContains(page, '<code>[[../Sales]]</code> is <code>/sales</code>')

    def test_a_folder_says_so_and_what_is_in_it(self):
        engineering = self.make_page('Engineering', body='How we work.', folder=True)

        response = self.client.get(engineering.get_absolute_url())

        self.assertContains(response, '>Folder</span>')
        self.assertContains(response, 'In this folder')
        self.assertContains(response, 'Nothing in it yet')
        self.assertContains(response, 'New page in this folder')
        self.assertNotContains(self.client.get(self.make_page('Platform').get_absolute_url()), '>Folder</span>')

    def test_a_page_started_at_a_folder_s_address_is_a_folder(self):
        self.client.post('/dg/wiki/engineering/', {'title': 'Engineering'})

        self.assertTrue(Page.objects.get(path='engineering').folder)


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

        self.assertContains(response, 'Maak er een map van')
        self.assertContains(response, 'Laatst gewijzigd door Anna Tester')
