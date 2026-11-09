import io
import shutil
import tempfile
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from datagroceries.wiki import search
from datagroceries.wiki.forms import fingerprint
from datagroceries.wiki.models import Page
from datagroceries.wiki.tests.test_pages import WikiTestCase


class SearchTests(WikiTestCase):
    def test_pages_with_every_word_title_matches_first(self):
        self.make_page('Onboarding', body='Read how we deploy on the first day.')
        self.make_page('Deploying', body='Pull, migrate, restart. Do not deploy on Friday.')
        self.make_page('Holidays', body='Friday afternoons are free.')

        self.assertEqual([hit.page.title for hit in search.search('deploy')], ['Deploying', 'Onboarding'])
        self.assertEqual([hit.page.title for hit in search.search('deploy friday')], ['Deploying'])

    def test_a_hit_shows_the_text_around_the_word_marked_and_escaped(self):
        page = self.make_page('Notes', body='## Intro\n\n' + 'word ' * 30 + 'the **<b>Deploy</b>** step.')

        [hit] = search.search('deploy')

        self.assertEqual(hit.page, page)
        self.assertIn('&lt;b&gt;<mark>Deploy</mark>&lt;/b&gt; step.', hit.snippet)
        self.assertTrue(hit.snippet.startswith('…'))
        self.assertNotIn('**', hit.snippet)

    def test_the_search_page(self):
        self.make_page('Deploying')

        response = self.client.get(reverse('dg_wiki:search'), {'q': 'deploy'})

        self.assertContains(response, 'Pages with “deploy”')
        self.assertContains(response, 'href="/dg/wiki/deploying"')
        self.assertContains(self.client.get(reverse('dg_wiki:search'), {'q': 'nothing'}), 'No page holds')


class ExportTests(WikiTestCase):
    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media)
        settings = override_settings(MEDIA_ROOT=media)
        settings.enable()
        self.addCleanup(settings.disable)
        self.engineering = self.make_page('Engineering', body='See [[./Deploying]], [[../Onboarding]] and [[Nowhere]].')
        self.deploying = self.make_page('Deploying', self.engineering, body='Back to [[.|the folder]]. `[[Code]]`')
        self.make_page('Onboarding')

    def test_a_page_without_pages_under_it_is_one_markdown_file(self):
        response = self.client.get(reverse('dg_wiki:page_export', args=[self.deploying.path]))

        self.assertEqual(response['Content-Disposition'], 'attachment; filename="deploying.md"')
        self.assertEqual(
            response.content.decode(),
            '# Deploying\n\nBack to [the folder](http://testserver/dg/wiki/engineering/). `[[Code]]`\n',
        )

    def test_a_page_with_pages_under_it_is_a_zip_with_links_between_its_files(self):
        upload = SimpleUploadedFile('shot.png', b'\x89PNG', 'image/png')
        image = self.client.post(reverse('dg_wiki:page_upload', args=[self.deploying.path]), {'image': upload})
        self.deploying.body += f'\n\n![shot]({image.json()["data"]["filePath"]})'
        self.deploying.save()

        response = self.client.get(reverse('dg_wiki:page_export', args=[self.engineering.path]))

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        attachment = self.deploying.attachments.get()
        file_name = f'engineering/deploying.files/{attachment.pk}-shot.png'
        self.assertEqual(
            sorted(archive.namelist()), sorted(['engineering/index.md', 'engineering/deploying.md', file_name])
        )
        self.assertEqual(
            archive.read('engineering/index.md').decode(),
            '# Engineering\n\nSee [Deploying](deploying.md), '
            '[Onboarding](http://testserver/dg/wiki/onboarding) and Nowhere.\n',
        )
        deploying = archive.read('engineering/deploying.md').decode()
        self.assertIn('Back to [the folder](index.md).', deploying)
        self.assertIn(f'![shot](deploying.files/{attachment.pk}-shot.png)', deploying)
        self.assertEqual(archive.read(file_name), b'\x89PNG')

    def test_the_whole_wiki(self):
        response = self.client.get(reverse('dg_wiki:wiki_export'))

        names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
        self.assertEqual(sorted(names), ['engineering/deploying.md', 'engineering/index.md', 'onboarding.md'])


@override_settings(LANGUAGES=[('en', 'English'), ('nl', 'Nederlands'), ('de', 'Deutsch')])
class LanguageTests(WikiTestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_page('Deploying', body='Pull, then restart.')
        Page.objects.filter(pk=self.page.pk).update(language='en')
        self.page.refresh_from_db()

    def translate(self, page, language, title):
        return self.client.post(
            reverse('dg_wiki:page_translate', args=[page.path]), {'language': language, 'title': title}
        )

    def test_a_translation_starts_from_the_text_beside_its_page(self):
        response = self.translate(self.page, 'nl', 'Uitrollen')

        made = Page.objects.get(title='Uitrollen')
        self.assertRedirects(response, '/dg/wiki/uitrollen/-/edit/', fetch_redirect_response=False)
        self.assertEqual(
            (made.language, made.original, made.body, made.parent), ('nl', self.page, self.page.body, None)
        )

    def test_each_language_of_a_page_links_to_the_others(self):
        self.translate(self.page, 'nl', 'Uitrollen')
        dutch = Page.objects.get(title='Uitrollen')
        self.translate(dutch, 'de', 'Ausrollen')

        self.assertEqual(Page.objects.get(title='Ausrollen').original, self.page)
        response = self.client.get(dutch.get_absolute_url())
        self.assertContains(response, 'hreflang="en">English</a>')
        self.assertContains(response, 'hreflang="de">Deutsch</a>')
        self.assertContains(response, 'lang="nl"')

    def test_a_language_the_page_is_in_already_is_not_offered(self):
        self.translate(self.page, 'nl', 'Uitrollen')

        response = self.translate(self.page, 'nl', 'Nog een keer')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Page.objects.filter(title='Nog een keer').exists())

    def test_a_translation_says_when_its_original_changed_after_it(self):
        self.translate(self.page, 'nl', 'Uitrollen')
        dutch = Page.objects.get(title='Uitrollen')
        self.assertNotContains(self.client.get(dutch.get_absolute_url()), 'changed after this page did')

        self.client.post(
            reverse('dg_wiki:page_edit', args=[self.page.path]),
            {
                'title': 'Deploying',
                'body': 'Pull, migrate, restart.',
                'language': 'en',
                'original': fingerprint(self.page),
            },
        )

        self.assertContains(self.client.get(dutch.get_absolute_url()), 'changed after this page did')

    def test_deleting_the_original_keeps_the_translations_together(self):
        self.translate(self.page, 'nl', 'Uitrollen')
        self.translate(self.page, 'de', 'Ausrollen')
        dutch, german = Page.objects.get(title='Uitrollen'), Page.objects.get(title='Ausrollen')

        self.client.post(reverse('dg_wiki:page_delete', args=[self.page.path]))

        dutch.refresh_from_db()
        german.refresh_from_db()
        self.assertEqual((dutch.original, german.original), (None, dutch))
