"""Tests for the ways into the API and the MCP endpoint (datagroceries.core.authentication)."""

import dataclasses
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.test import APIClient

from datagroceries.core import areas, authentication
from datagroceries.core.tests import person

NOTES = areas.Area(scope='notes', label='Notes', permission='auth.view_group', instructions='Notes.')
LISTS = areas.Area(scope='lists', label='Lists', permission='auth.view_group', instructions='Lists.')
LIST_TOOLS = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}


@dataclasses.dataclass
class OAuthToken:
    """An OAuth access token as django-oauth-toolkit gives it: its scope a space-separated string."""

    scope: str
    application: object = None


class OAuthLike(BaseAuthentication):
    """A registered way in, for the tests: `Bearer oauth:<username>:<scope>`."""

    def authenticate(self, request):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer oauth:'):
            return None
        _, username, scope = header.removeprefix('Bearer ').split(':')
        app = mock.Mock()
        app.name = 'Claude'
        return get_user_model().objects.get(username=username), OAuthToken(scope.replace('+', ' '), app)


class HostBearer(BaseAuthentication):
    """A host project's own Bearer tokens, such as JWTs: `Bearer host-<username>`."""

    def authenticate(self, request):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer host-'):
            return None
        return get_user_model().objects.get(username=header.removeprefix('Bearer host-')), 'a host token'


@mock.patch.dict(areas.AREAS, {'notes': NOTES, 'lists': LISTS}, clear=True)
@override_settings(DG_AUTHENTICATION_CLASSES=['datagroceries.core.tests.test_authentication.HostBearer'])
class WaysInTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = person('auth.view_group', username='anna')

    def setUp(self):
        self.client = APIClient()
        patcher = mock.patch.object(authentication, '_ways_in', [OAuthLike])
        patcher.start()
        self.addCleanup(patcher.stop)

    def open_areas(self, header: str) -> list[str] | int:
        self.client.credentials(HTTP_AUTHORIZATION=header)
        response = self.client.post('/dg/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'}, format='json')
        if response.status_code != 200:
            return response.status_code
        return [line for line in ('Notes.', 'Lists.') if line in response.json()['result']['instructions']]

    def test_the_host_project_s_own_bearer_tokens_come_after_the_registered_ways_in(self):
        self.assertEqual(self.open_areas('Bearer host-anna'), ['Notes.', 'Lists.'])

    def test_an_oauth_token_opens_what_its_scope_covers_and_its_person_may_use(self):
        self.assertEqual(self.open_areas('Bearer oauth:anna:notes'), ['Notes.'])
        self.assertEqual(self.open_areas('Bearer oauth:anna:notes+lists'), ['Notes.', 'Lists.'])
        self.user.user_permissions.clear()
        self.assertEqual(self.open_areas('Bearer oauth:anna:notes+lists'), [])

    def test_nothing_that_lets_it_in_is_a_401(self):
        self.assertEqual(self.open_areas('Bearer nobody-knows-this'), 401)

    def test_a_signed_in_session_does_not_open_the_api(self):
        self.client.credentials()
        self.client.force_login(self.user)

        self.assertEqual(self.open_areas(''), 401)


@mock.patch.dict(areas.AREAS, {'notes': NOTES}, clear=True)
class DiscoveryTests(TestCase):
    @mock.patch.object(authentication, '_authorization_servers', [])
    def test_without_an_authorization_server_a_401_points_nowhere(self):
        response = APIClient().post('/dg/mcp', LIST_TOOLS, format='json')

        self.assertEqual((response.status_code, response['WWW-Authenticate']), (401, 'Bearer'))
        self.assertEqual(self.client.get('/dg/.well-known/oauth-protected-resource').status_code, 404)

    @override_settings(DG_AUTHORIZATION_SERVER='https://login.example.com')
    def test_a_401_points_at_the_metadata_which_names_the_authorization_server(self):
        response = APIClient().post('/dg/mcp', LIST_TOOLS, format='json')
        metadata = self.client.get('/dg/.well-known/oauth-protected-resource').json()

        self.assertEqual(
            response['WWW-Authenticate'],
            'Bearer resource_metadata="http://testserver/dg/.well-known/oauth-protected-resource"',
        )
        self.assertEqual(metadata['resource'], 'http://testserver/dg/mcp')
        self.assertEqual(metadata['authorization_servers'], ['https://login.example.com'])
        self.assertEqual(metadata['scopes_supported'], ['notes'])
