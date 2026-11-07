from django.urls import reverse

from gilde.core import markdown
from gilde.wiki.models import Link, Page
from gilde.wiki.tests.test_pages import WikiTestCase


class LinkTests(WikiTestCase):
    def setUp(self):
        super().setUp()
        self.engineering = self.make_page('Engineering')
        self.deploying = self.make_page('Deploying', self.engineering)

    def test_a_link_names_a_page_by_its_address_in_titles_or_slugs(self):
        html = markdown.render('[[Engineering/Deploying]] and [[engineering/deploying|how we ship]]')

        link = '<a href="/gilde/wiki/engineering/deploying/" rel="noopener noreferrer">{}</a>'
        self.assertInHTML(link.format('Deploying'), html)
        self.assertInHTML(link.format('how we ship'), html)

    def test_the_end_of_an_address_will_do_and_the_highest_page_wins(self):
        self.make_page('Deploying', self.make_page('Archive', self.make_page('Old')))

        html = markdown.render('See [[Deploying]].')

        self.assertInHTML('<a href="/gilde/wiki/engineering/deploying/" rel="noopener noreferrer">Deploying</a>', html)

    def test_a_link_to_no_page_offers_to_start_it(self):
        html = markdown.render('[[Engineering/Release notes]]')

        self.assertInHTML(
            '<a class="wk-missing" href="/gilde/wiki/engineering/release-notes/?title=Release+notes" '
            'title="No such page yet" rel="noopener noreferrer">Engineering/Release notes</a>',
            html,
        )
        response = self.client.get('/gilde/wiki/engineering/release-notes/?title=Release+notes')
        self.assertContains(response, 'value="Release notes"', status_code=404)

    def test_links_in_code_and_tickets_keys_inside_a_link_are_left_alone(self):
        html = markdown.render('`[[Deploying]]` and [[Deploying|before T-1]]')

        self.assertIn('<code>[[Deploying]]</code>', html)
        self.assertInHTML('<a href="/gilde/wiki/engineering/deploying/" rel="noopener noreferrer">before T-1</a>', html)

    def test_a_page_lists_the_pages_that_link_to_it(self):
        self.make_page('Onboarding', body='Read [[Deploying]] first.')
        self.make_page('Code', body='`[[Deploying]]` is how a link is written.')

        response = self.client.get(self.deploying.get_absolute_url())

        self.assertEqual([page.title for page in response.context['backlinks']], ['Onboarding'])
        self.assertContains(response, 'Pages that link here')

    def test_a_link_finds_its_page_once_the_page_is_made(self):
        onboarding = self.make_page('Onboarding', body='[[Release notes]]')
        self.assertIsNone(Link.objects.get(source=onboarding).target)

        notes = self.make_page('Release notes')

        self.assertEqual(Link.objects.get(source=onboarding).target, notes)

    def test_links_follow_a_renamed_page_in_the_way_they_were_written(self):
        onboarding = self.make_page(
            'Onboarding',
            body='[[Deploying]], [[Engineering/Deploying|ship]], [[engineering/deploying]], `[[Deploying]]`',
        )

        self.deploying.title = 'Shipping'
        self.deploying.save()

        onboarding.refresh_from_db()
        self.assertEqual(
            onboarding.body, '[[Shipping]], [[Engineering/Shipping|ship]], [[engineering/shipping]], `[[Deploying]]`'
        )
        self.assertEqual(onboarding.history.count(), 2)

    def test_links_follow_the_pages_under_a_moved_page(self):
        rollback = self.make_page('Rollback', self.deploying)
        operations = self.make_page('Operations')
        onboarding = self.make_page('Onboarding', body='[[Deploying/Rollback]] and [[Engineering/Deploying]]')

        self.deploying.parent = operations
        self.deploying.save()

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.body, '[[Deploying/Rollback]] and [[Operations/Deploying]]')
        self.assertEqual(Link.objects.get(source=onboarding, reference='deploying/rollback').target, rollback)

    def test_a_link_grows_longer_when_its_end_would_name_another_page(self):
        self.make_page('Shipping')
        onboarding = self.make_page('Onboarding', body='[[Deploying]]')

        self.deploying.title = 'Shipping'
        self.deploying.save()

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.body, '[[Engineering/Shipping]]')

    def test_a_link_in_a_page_to_itself_follows_it(self):
        self.deploying.body = 'This is [[Engineering/Deploying]].'
        self.deploying.save()

        self.deploying.title = 'Shipping'
        self.deploying.save()

        self.assertEqual(self.deploying.body, 'This is [[Engineering/Shipping]].')
        self.assertEqual(Page.objects.get(pk=self.deploying.pk).body, self.deploying.body)

    def test_a_title_a_link_cannot_hold_is_written_as_its_slug(self):
        onboarding = self.make_page('Onboarding', body='[[Deploying]]')

        self.deploying.title = 'CI/CD'
        self.deploying.save()

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.body, '[[cicd]]')


class ArrangeTests(WikiTestCase):
    def setUp(self):
        super().setUp()
        self.first = self.make_page('First')
        self.second = self.make_page('Second')
        self.third = self.make_page('Third')
        for position, page in enumerate((self.first, self.second, self.third), start=1):
            Page.objects.filter(pk=page.pk).update(position=position)

    def arrange(self, page, parent=None, before=None, current=None):
        data = {'page': page.pk, 'parent': parent.pk if parent else '', 'before': before.pk if before else ''}
        if current:
            data['current'] = current.pk
        return self.client.post(reverse('gilde_wiki:tree_arrange'), data)

    def titles(self, parent=None):
        return list(Page.objects.filter(parent=parent).values_list('title', flat=True))

    def test_a_page_dragged_before_another_goes_there(self):
        response = self.arrange(self.third, before=self.first)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(), ['Third', 'First', 'Second'])
        self.assertIn('data-page', response.json()['tree'])

    def test_a_page_dragged_after_the_last_goes_last(self):
        self.arrange(self.first)

        self.assertEqual(self.titles(), ['Second', 'Third', 'First'])

    def test_reordering_makes_no_history(self):
        self.arrange(self.third, before=self.first)

        self.assertEqual(self.third.history.count(), 1)

    def test_a_page_dragged_onto_another_goes_under_it_and_its_address_follows(self):
        response = self.arrange(self.third, parent=self.first, current=self.third)

        self.assertEqual(self.titles(self.first), ['Third'])
        self.assertEqual(response.json()['url'], '/gilde/wiki/first/third/')

    def test_a_page_cannot_be_dragged_under_itself_or_beside_a_page_elsewhere(self):
        under = self.make_page('Under', self.first)

        self.assertEqual(self.arrange(self.first, parent=under).status_code, 400)
        self.assertEqual(self.arrange(self.second, before=under).status_code, 400)
        self.assertEqual(self.titles(), ['First', 'Second', 'Third'])
