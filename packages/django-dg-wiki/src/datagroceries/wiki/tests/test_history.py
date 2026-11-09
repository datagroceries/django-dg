import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from datagroceries.wiki.compare import side_by_side
from datagroceries.wiki.forms import fingerprint
from datagroceries.wiki.models import Attachment, Page
from datagroceries.wiki.tests.test_pages import WikiTestCase


class CompareTests(WikiTestCase):
    def test_the_words_that_changed_are_marked_and_long_unchanged_stretches_folded(self):
        before = '\n'.join(f'line {number}' for number in range(1, 21))
        after = before.replace('line 10', 'line ten')

        rows = side_by_side(before, after)

        self.assertEqual([row.kind for row in rows], ['folded', *['same'] * 3, 'changed', *['same'] * 3, 'folded'])
        self.assertEqual((rows[0].folded, rows[-1].folded), (6, 7))
        self.assertEqual(rows[4].left, 'line <del>10</del>')
        self.assertEqual(rows[4].right, 'line <ins>ten</ins>')

    def test_a_new_line_stands_alone_and_each_changed_line_is_beside_its_like(self):
        rows = side_by_side(
            '1. Pull.\n2. Restart the service.', '1. Tell the team.\n2. Pull.\n3. Restart the service and workers.'
        )

        self.assertEqual([row.kind for row in rows], ['added', 'changed', 'changed'])
        self.assertEqual(rows[1].right, '<ins>2</ins>. Pull.')

    def test_lines_added_and_removed_stand_alone_and_text_is_escaped(self):
        rows = side_by_side('one\n<b>two</b>', 'one')

        self.assertEqual(rows[-1].kind, 'removed')
        self.assertEqual(rows[-1].left, '<del>&lt;b&gt;two&lt;/b&gt;</del>')
        self.assertIsNone(rows[-1].right)


class HistoryTests(WikiTestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_page('Deploying', body='Pull, then restart.')
        self.edit('Deploying', 'Pull, migrate, then restart.')
        self.edit('Shipping', 'Pull, migrate, then restart.')

    def edit(self, title, body):
        self.page.refresh_from_db()
        self.client.post(
            reverse('dg_wiki:page_edit', args=[self.page.path]),
            {'title': title, 'body': body, 'original': fingerprint(self.page)},
        )
        self.page.refresh_from_db()

    def versions(self):
        return list(self.page.history.order_by('history_date', 'history_id'))

    def test_the_history_says_who_changed_what(self):
        response = self.client.get(reverse('dg_wiki:page_history', args=[self.page.path]))

        self.assertContains(response, 'Created')
        self.assertContains(response, 'Text changed')
        self.assertContains(response, 'Renamed to “Shipping”')

    def test_a_version_is_compared_with_the_one_before_it(self):
        created, migrated, _renamed = self.versions()

        response = self.client.get(reverse('dg_wiki:page_compare', args=[self.page.path, migrated.history_id]))

        self.assertContains(response, 'Pull<ins>, migrate</ins>, then restart.', html=False)
        self.assertEqual(response.context['older']['record'], created)

    def test_a_version_compared_with_now_puts_the_older_left(self):
        created, _migrated, renamed = self.versions()
        url = reverse('dg_wiki:page_compare', args=[self.page.path, renamed.history_id])

        response = self.client.get(f'{url}?with={created.history_id}')

        self.assertEqual(response.context['older']['record'], created)
        self.assertTrue(response.context['title_changed'])
        self.assertTrue(response.context['newer']['current'])

    def test_bringing_a_version_back_makes_a_new_one(self):
        created = self.versions()[0]

        self.client.post(reverse('dg_wiki:page_restore', args=[self.page.path, created.history_id]))

        self.page.refresh_from_db()
        self.assertEqual((self.page.title, self.page.body), ('Deploying', 'Pull, then restart.'))
        self.assertEqual(self.page.path, 'deploying')
        latest = self.page.history.first()
        self.assertEqual(latest.restored_from, created.history_id)
        self.assertEqual(latest.history_user, self.user)
        history = self.client.get(reverse('dg_wiki:page_history', args=[self.page.path]))
        self.assertContains(history, 'Brought back the version of')

    def test_a_page_that_only_holds_others_lists_them(self):
        self.make_page('Rollback', self.page)

        response = self.client.get(self.page.get_absolute_url())
        self.assertNotContains(response, 'wk-index')

        Page.objects.filter(pk=self.page.pk).update(body='')
        response = self.client.get(self.page.get_absolute_url())
        self.assertContains(response, '<ul class="wk-index"><li><a href="/dg/wiki/shipping/rollback">Rollback</a>')


class FileTests(WikiTestCase):
    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media)
        settings = override_settings(MEDIA_ROOT=media)
        settings.enable()
        self.addCleanup(settings.disable)
        self.page = self.make_page('Deploying')

    def test_an_image_pasted_into_the_editor_is_kept_with_the_page(self):
        upload = SimpleUploadedFile('Screen shot (1).PNG', b'\x89PNG', 'image/png')

        answer = self.client.post(reverse('dg_wiki:page_upload', args=[self.page.path]), {'image': upload}).json()

        attachment = self.page.attachments.get()
        self.assertEqual(answer['data']['filePath'], f'/dg/wiki/-/files/{attachment.pk}/screen-shot-1.png')
        response = self.client.get(answer['data']['filePath'])
        self.assertEqual(response['Content-Type'], 'image/png')

    def test_a_file_beside_the_page_is_served_as_a_download(self):
        upload = SimpleUploadedFile('page.html', b'<script></script>', 'text/html')

        self.client.post(reverse('dg_wiki:page_attach', args=[self.page.path]), {'file': upload})

        attachment = self.page.attachments.get()
        page = self.client.get(self.page.get_absolute_url())
        self.assertContains(page, 'page.html')
        response = self.client.get(attachment.get_absolute_url())
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_deleting_a_page_deletes_its_files(self):
        upload = SimpleUploadedFile('notes.txt', b'notes', 'text/plain')
        self.client.post(reverse('dg_wiki:page_attach', args=[self.page.path]), {'file': upload})
        storage = Attachment.objects.get().file.storage
        name = Attachment.objects.get().file.name

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('dg_wiki:page_delete', args=[self.page.path]))

        self.assertFalse(Attachment.objects.exists())
        self.assertFalse(storage.exists(name))
