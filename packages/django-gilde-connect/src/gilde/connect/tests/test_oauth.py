"""Tests for OAuth for the Claude connector (gilde.connect.oauth): from the MCP endpoint's 401 to a
connected app using the tools, as a Claude client goes through it."""

import base64
import hashlib
import html
import re
import secrets
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core import checks
from django.test import TestCase
from django.urls import reverse
from oauth2_provider.cimd import SafeMetadataFetcher
from oauth2_provider.models import AccessToken, RefreshToken, get_application_model
from rest_framework.test import APIClient

from gilde.connect.oauth import OfferedGrantsMetadataFetcher
from gilde.core import areas
from gilde.core.tests import person

NOTES = areas.Area(scope='notes', label='Notes', permission='auth.view_group', instructions='Notes.')
REDIRECT = 'http://127.0.0.1:53111/callback'


@mock.patch.dict(areas.AREAS, {'notes': NOTES}, clear=True)
class DiscoveryTests(TestCase):
    def test_a_client_given_only_the_endpoint_finds_where_to_sign_in(self):
        unauthorized = APIClient().post('/gilde/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, format='json')
        pointer = re.search(r'resource_metadata="([^"]+)"', unauthorized['WWW-Authenticate'])[1]
        resource = self.client.get(pointer).json()
        [issuer] = resource['authorization_servers']
        metadata = self.client.get(f'{urlparse(issuer).path}/.well-known/oauth-authorization-server').json()
        where_mcp_looks = self.client.get(f'{urlparse(issuer).path}/.well-known/openid-configuration').json()

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(resource['resource'], 'http://testserver/gilde/mcp')
        self.assertEqual(issuer, 'http://testserver/gilde/connect')
        self.assertEqual(metadata, where_mcp_looks)
        self.assertEqual(metadata['issuer'], issuer)
        self.assertEqual(metadata['authorization_endpoint'], 'http://testserver/gilde/connect/oauth/authorize/')
        self.assertEqual(metadata['token_endpoint'], 'http://testserver/gilde/connect/oauth/token/')
        self.assertTrue(metadata['client_id_metadata_document_supported'])
        self.assertEqual(metadata['code_challenge_methods_supported'], ['S256'])
        self.assertEqual(metadata['token_endpoint_auth_methods_supported'], ['none'])
        self.assertNotIn('registration_endpoint', metadata)


@mock.patch.dict(areas.AREAS, {'notes': NOTES}, clear=True)
class FlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = person('auth.view_group', username='anna@example.com', first_name='Anna', last_name='Smit')
        # As the toolkit makes one from a Client ID Metadata Document: public, PKCE instead of a secret.
        cls.app = get_application_model().objects.create(
            name='Claude',
            client_type='public',
            authorization_grant_type='authorization-code',
            redirect_uris='http://127.0.0.1/callback',
        )

    def sign_in(self) -> dict:
        """Through the consent page to tokens, as a client on a loopback port does."""
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.client.force_login(self.user)
        page = self.client.get(
            reverse('oauth2_provider:authorize'),
            {
                'response_type': 'code',
                'client_id': self.app.client_id,
                'redirect_uri': REDIRECT,
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
                'state': 'abc',
            },
        )
        self.assertContains(page, 'Connect Claude')
        # By name, not by a username that may be an email address.
        self.assertContains(page, 'act as you, Anna Smit, in:')
        self.assertContains(page, '<span class="navbar-text py-0">Anna Smit</span>', html=False)
        self.assertContains(page, '<li>Notes</li>')
        self.assertContains(page, 'you go back to <strong>127.0.0.1</strong>')
        hidden = re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', page.content.decode())
        form = {name: html.unescape(value) for name, value in hidden}
        allowed = self.client.post(reverse('oauth2_provider:authorize'), {**form, 'allow': 'on'})
        self.assertTrue(allowed['Location'].startswith(REDIRECT))
        code = parse_qs(urlparse(allowed['Location']).query)['code'][0]
        return (
            APIClient()
            .post(
                reverse('oauth2_provider:token'),
                {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': REDIRECT,
                    'client_id': self.app.client_id,
                    'code_verifier': verifier,
                },
            )
            .json()
        )

    def tools(self, access_token: str) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        return client

    def initialize(self, client) -> str:
        response = client.post('/gilde/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'}, format='json')
        return response.json()['result']['instructions'] if response.status_code == 200 else response.status_code

    def test_a_connected_app_works_as_its_person_and_its_refresh_token_turns_over(self):
        tokens = self.sign_in()

        self.assertEqual(tokens['scope'], 'notes')
        self.assertIn('Notes.', self.initialize(self.tools(tokens['access_token'])))
        refreshed = (
            APIClient()
            .post(
                reverse('oauth2_provider:token'),
                {
                    'grant_type': 'refresh_token',
                    'refresh_token': tokens['refresh_token'],
                    'client_id': self.app.client_id,
                },
            )
            .json()
        )
        self.assertNotEqual(refreshed['refresh_token'], tokens['refresh_token'])

    def test_it_loses_an_app_when_its_person_does(self):
        client = self.tools(self.sign_in()['access_token'])
        self.user.user_permissions.clear()

        self.assertNotIn('Notes.', self.initialize(client))

    def test_it_is_listed_and_disconnected_on_the_connect_page(self):
        client = self.tools(self.sign_in()['access_token'])

        self.assertContains(self.client.get(reverse('gilde_connect:connect')), '<strong>Claude</strong>')
        self.client.post(reverse('gilde_connect:connection_revoke', args=[self.app.pk]))

        self.assertEqual(self.initialize(client), 401)
        self.assertFalse(AccessToken.objects.exists())
        self.assertFalse(RefreshToken.objects.filter(revoked=None).exists())
        self.assertNotContains(self.client.get(reverse('gilde_connect:connect')), '<strong>Claude</strong>')

    def test_someone_who_may_use_nothing_is_told_so(self):
        self.client.force_login(person(username='visitor'))

        response = self.client.get(reverse('oauth2_provider:authorize'), {'client_id': self.app.client_id})

        self.assertContains(response, 'Nothing to connect to', status_code=403)


class ClientDocumentTests(TestCase):
    def test_grants_not_offered_are_dropped_from_a_client_s_document(self):
        claude = {'client_name': 'Claude', 'grant_types': ['authorization_code', 'refresh_token', 'jwt-bearer']}
        with mock.patch.object(SafeMetadataFetcher, 'fetch', return_value=(claude, 300)):
            metadata, _max_age = OfferedGrantsMetadataFetcher().fetch('https://claude.ai/oauth/client')

        self.assertEqual(metadata['grant_types'], ['authorization_code', 'refresh_token'])


class SettingsTests(TestCase):
    def test_the_oauth_settings_pass_the_toolkit_s_deploy_checks(self):
        found = checks.run_checks(include_deployment_checks=True)

        # Errors only: the warning about http redirect URIs is the price of Claude Code's loopback.
        self.assertEqual([check.id for check in found if check.id.startswith('oauth2_provider.E')], [])
