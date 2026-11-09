"""The wiki's REST API through its MCP tools (datagroceries.wiki.api, datagroceries.wiki.mcp), as an agent uses it."""

import json

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from datagroceries.core.tests import TEST_AUTHENTICATION, issue
from datagroceries.wiki import search
from datagroceries.wiki.models import Page
from datagroceries.wiki.tests import member, serving

URL = '/dg/mcp/'


def token_client(user, scopes=('wiki',)) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(user, "Claude", scopes)}')
    return client


def call(client, method, params=None):
    message = {'jsonrpc': '2.0', 'id': 1, 'method': method, **({'params': params} if params is not None else {})}
    return client.post(URL, json.dumps(message), content_type='application/json')


def tool(client, name, **arguments) -> tuple[dict, bool]:
    """Call a tool; what it answered, and whether that was an error."""
    result = call(client, 'tools/call', {'name': name, 'arguments': arguments}).json()['result']
    text = result['content'][0]['text']
    return (json.loads(text) if text else None), result['isError']


@override_settings(DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
class WikiToolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = member(username='anna', email='anna@example.com', first_name='Anna')

    def setUp(self):
        self.client = token_client(self.user)
        self.engineering = Page.objects.create(title='Engineering', creator=self.user, folder=True)
        self.deploying = Page.objects.create(
            title='Deploying', parent=self.engineering, creator=self.user, body='Pull, then restart.'
        )

    def test_a_wiki_token_gets_the_wiki_s_tools_and_no_others(self):
        names = {each['name'] for each in call(self.client, 'tools/list').json()['result']['tools']}

        self.assertIn('get_page', names)
        self.assertIn('update_page', names)
        self.assertNotIn('get_ticket', names)
        board_only = token_client(self.user, scopes=('board',))
        self.assertNotIn(
            'get_page', {each['name'] for each in call(board_only, 'tools/list').json()['result']['tools']}
        )

    def test_a_page_is_found_by_its_whole_address_in_titles_or_slugs(self):
        page, error = tool(self.client, 'get_page', path='Engineering/Deploying')

        self.assertFalse(error)
        self.assertEqual(
            (page['path'], page['body'], page['parent']),
            ('engineering/deploying', 'Pull, then restart.', 'engineering'),
        )
        self.assertEqual(page['last_changed']['by']['handle'], 'anna')
        self.assertEqual(tool(self.client, 'get_page', path='nowhere')[1], True)
        self.assertEqual(tool(self.client, 'get_page', path='Deploying')[1], True)

    def test_a_change_from_an_old_version_is_refused_and_from_the_latest_goes_through(self):
        version = tool(self.client, 'get_page', path='engineering/deploying')[0]['version']
        Page.objects.get(pk=self.deploying.pk).save()  # someone else saves meanwhile

        answer, error = tool(
            self.client, 'update_page', path='Engineering/Deploying', body='Pull, migrate.', version=version
        )
        self.assertTrue(error)
        self.assertIn('changed since version', answer['detail'])

        latest = tool(self.client, 'get_page', path='Engineering/Deploying')[0]['version']
        answer, error = tool(
            self.client, 'update_page', path='Engineering/Deploying', body='Pull, migrate.', version=latest
        )
        self.assertFalse(error)
        self.assertEqual(answer['body'], 'Pull, migrate.')
        self.assertEqual(answer['last_changed']['via'], 'Claude')

    def test_create_move_and_order(self):
        page, error = tool(self.client, 'create_page', title='Rollback', parent='Engineering', body='Revert.')
        self.assertFalse(error)
        self.assertEqual(page['path'], 'engineering/rollback')

        page, _error = tool(self.client, 'update_page', path='Engineering/Rollback', before='Engineering/Deploying')
        self.assertEqual(
            [child['title'] for child in tool(self.client, 'get_page', path='Engineering')[0]['children']],
            ['Rollback', 'Deploying'],
        )

        page, _error = tool(self.client, 'update_page', path='Engineering/Rollback', parent=None)
        self.assertEqual(page['path'], 'rollback')
        answer, error = tool(self.client, 'update_page', path='Engineering', parent='Engineering/Deploying')
        self.assertTrue(error)
        self.assertIn('parent', answer)

    def test_a_folder_is_made_and_a_page_made_one(self):
        folder, error = tool(self.client, 'create_page', title='Operations', folder=True)
        self.assertFalse(error)
        self.assertTrue(folder['folder'])
        self.assertTrue(folder['url'].endswith('/dg/wiki/operations/'))

        page, error = tool(self.client, 'update_page', path='Engineering/Deploying', folder=True)
        self.assertFalse(error)
        self.assertTrue(page['folder'])
        answer, error = tool(self.client, 'update_page', path='Engineering', folder=False)
        self.assertTrue(error)
        self.assertIn('folder', answer)

    def test_a_page_in_another_language_is_linked_and_unlinked(self):
        Page.objects.filter(pk=self.deploying.pk).update(language='en')
        dutch = Page.objects.create(title='Uitrollen', parent=self.engineering, creator=self.user, language='nl')

        page, error = tool(self.client, 'translate_page', path='Engineering/Deploying', page='Engineering/Uitrollen')

        self.assertFalse(error)
        self.assertEqual(
            page['translations'], [{'path': 'engineering/uitrollen', 'title': 'Uitrollen', 'language': 'nl'}]
        )
        page, error = tool(self.client, 'unlink_page_translation', path='Engineering/Uitrollen')
        self.assertFalse(error)
        dutch.refresh_from_db()
        self.assertIsNone(dutch.original)

    def test_search_and_the_tree(self):
        found, _error = tool(self.client, 'search_pages', q='restart')
        self.assertEqual([hit['path'] for hit in found['results']], ['engineering/deploying'])
        self.assertIn('restart', found['results'][0]['snippet'])

        tree, _error = tool(self.client, 'search_pages')
        self.assertEqual(
            [(page['path'], page['depth']) for page in tree['results']],
            [('engineering', 0), ('engineering/deploying', 1)],
        )

    def test_history_a_version_and_bringing_it_back(self):
        tool(self.client, 'update_page', path='Engineering/Deploying', body='Wrong.')
        history, _error = tool(self.client, 'get_page_history', path='Engineering/Deploying')
        first = history[-1]['version']
        self.assertEqual(
            tool(self.client, 'get_page_version', path='Engineering/Deploying', version=first)[0]['body'],
            'Pull, then restart.',
        )

        page, error = tool(self.client, 'restore_page_version', path='Engineering/Deploying', version=first)

        self.assertFalse(error)
        self.assertEqual(page['body'], 'Pull, then restart.')

    def test_comment_watch_translate_and_delete(self):
        comment, error = tool(self.client, 'comment_on_page', path='Engineering/Deploying', body='Looks right.')
        self.assertFalse(error)
        edited, _error = tool(
            self.client, 'edit_page_comment', path='Engineering/Deploying', comment_id=comment['id'], body='Right.'
        )
        self.assertEqual(edited['body'], 'Right.')
        self.assertEqual(tool(self.client, 'unwatch_page', path='Engineering/Deploying')[0]['watchers'], [])

        Page.objects.filter(pk=self.deploying.pk).update(language='en')
        with override_settings(LANGUAGES=[('en', 'English'), ('nl', 'Nederlands')]):
            dutch, error = tool(
                self.client, 'translate_page', path='Engineering/Deploying', language='nl', title='Uitrollen'
            )
        self.assertFalse(error)
        self.assertEqual(dutch['path'], 'engineering/uitrollen')

        answer, error = tool(self.client, 'delete_page', path='Engineering')
        self.assertTrue(error)
        self.assertIn('Move or delete the pages under this page first.', answer['detail'])
        self.assertEqual(tool(self.client, 'delete_page', path='engineering/uitrollen')[1], False)
        self.assertFalse(Page.objects.filter(path='engineering/uitrollen').exists())


class NamingTests(TestCase):
    def test_the_pages_that_name_a_word_outside_code(self):
        user = member(username='anna')
        Page.objects.create(title='Release', creator=user, body='Waits for T-12, not T-123.')
        Page.objects.create(title='Code', creator=user, body='`T-12` in code')
        Page.objects.create(title='Other', creator=user, body='About T-123.')

        with serving(user):
            self.assertEqual([place.title for place in search.naming('T-12')], ['Release'])
            self.assertEqual([place.url for place in search.naming('T-123')], ['/dg/wiki/other', '/dg/wiki/release'])
