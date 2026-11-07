from unittest import mock

from django.urls import reverse

from gilde.core import markdown
from gilde.wiki.forms import fingerprint
from gilde.wiki.models import Comment, Watcher
from gilde.wiki.tests import member
from gilde.wiki.tests.test_pages import WikiTestCase


@mock.patch('gilde.core.notifications.send_notification')
class CommentTests(WikiTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bob = member(username='bob', email='bob@example.com', first_name='Bob', last_name='Builder')

    def setUp(self):
        super().setUp()
        self.page = self.make_page('Deploying')

    def sent(self, task):
        """Each message as the people it went to and its summary, address and quote on lines of their own."""
        return [(tuple(call.args[0]), '\n'.join(call.args[1:])) for call in task.enqueue.call_args_list]

    def comment(self, body, parent=None):
        data = {'body': body, 'parent': parent.pk if parent else ''}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('gilde_wiki:comment_create', args=[self.page.path]), data)

    def test_a_comment_tells_the_watchers_but_not_its_author(self, task):
        Watcher.objects.create(page=self.page, user=self.bob)

        response = self.comment('Looks **good**')

        made = Comment.objects.get()
        self.assertRedirects(response, f'/gilde/wiki/deploying/#comment-{made.pk}', fetch_redirect_response=False)
        [(emails, message)] = self.sent(task)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('Anna Tester commented on Deploying', message)
        self.assertIn(f'/gilde/wiki/deploying/#comment-{made.pk}\n', message)
        self.assertTrue(Watcher.objects.filter(page=self.page, user=self.user).exists())
        page = self.client.get(self.page.get_absolute_url())
        self.assertContains(page, '<strong>good</strong>')

    def test_a_mention_tells_that_person_once_and_makes_them_watch(self, task):
        self.comment('@bob, can you check?')

        [(emails, message)] = self.sent(task)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('Anna Tester mentioned you on Deploying', message)
        self.assertTrue(Watcher.objects.filter(page=self.page, user=self.bob).exists())

    def test_a_reply_goes_under_its_comment_and_not_under_a_reply(self, task):
        self.comment('First')
        first = Comment.objects.get()
        self.comment('Second', parent=first)
        reply = Comment.objects.get(body='Second')

        self.assertEqual(reply.parent, first)
        self.comment('Third', parent=reply)
        self.assertFalse(Comment.objects.filter(body='Third').exists())

    def test_only_its_author_edits_a_comment_and_it_shows_as_edited(self, task):
        self.comment('Frist')
        made = Comment.objects.get()
        url = reverse('gilde_wiki:comment_edit', args=[self.page.path, made.pk])

        self.client.post(url, {'body': 'First'})
        self.client.force_login(self.bob)
        self.client.post(url, {'body': 'Bob was here'})

        made.refresh_from_db()
        self.assertEqual(made.body, 'First')
        self.assertContains(self.client.get(self.page.get_absolute_url()), 'edited')

    def test_watching_starts_and_stops(self, task):
        url = reverse('gilde_wiki:page_watch', args=[self.page.path])
        self.client.force_login(self.bob)

        self.client.post(url, {'watching': 'yes'})
        self.assertTrue(Watcher.objects.filter(page=self.page, user=self.bob).exists())
        self.client.post(url, {'watching': 'no'})
        self.assertFalse(Watcher.objects.filter(page=self.page, user=self.bob).exists())

    def test_a_mention_in_the_page_text_tells_only_the_newly_mentioned(self, task):
        url = reverse('gilde_wiki:page_edit', args=[self.page.path])
        for body in ('Ask @bob.', 'Ask @bob, again.'):
            self.page.refresh_from_db()
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(url, {'title': 'Deploying', 'body': body, 'original': fingerprint(self.page)})

        [(emails, message)] = self.sent(task)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('Anna Tester mentioned you in Deploying', message)

    def test_a_mention_shows_among_the_wiki_s_people(self, task):
        html = markdown.render('Hi @bob and @nobody', context={'scope': 'wiki'})

        self.assertIn('<span class="gilde-mention" title="Bob Builder">@bob</span>', html)
        self.assertIn('@nobody', html)
