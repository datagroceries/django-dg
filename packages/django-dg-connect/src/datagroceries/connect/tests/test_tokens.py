"""Tests for the "Connect an agent" page (datagroceries.connect.views) and the personal tokens' rules."""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy
from rest_framework.authentication import BaseAuthentication
from rest_framework.test import APIClient

from datagroceries.connect.models import ApiToken
from datagroceries.core import areas
from datagroceries.core.tests import person

# Two areas with permissions every project has: the notes for everyone here, the secrets for nobody. Their
# labels are translatable, as the apps' are.
NOTES = areas.Area(scope='notes', label=gettext_lazy('Notes'), permission='auth.view_group', instructions='Notes.')
SECRETS = areas.Area(scope='secrets', label='Secrets', permission='auth.delete_group', instructions='Secrets.')


@mock.patch.dict(areas.AREAS, {'notes': NOTES, 'secrets': SECRETS}, clear=True)
class TokenPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = person('auth.view_group', username='anna', email='anna@example.com')

    def setUp(self):
        self.client.force_login(self.user)

    def test_a_token_is_made_for_the_areas_the_person_may_use_and_its_key_shown_once(self):
        page = self.client.get(reverse('dg_connect:connect'))
        made = self.client.post(reverse('dg_connect:token_create'), {'name': 'Laptop', 'scopes': ['notes'], 'days': 0})

        self.assertContains(page, 'value="notes"')
        self.assertContains(page, '{"servers": {"datagroceries": {"type": "http", "url": "http://testserver/dg/mcp"}}}')
        self.assertNotContains(page, 'value="secrets"')
        token = ApiToken.objects.get()
        self.assertEqual(
            (token.user, token.name, token.scopes, token.expires_at), (self.user, 'Laptop', ['notes'], None)
        )
        key = made.context['key']
        self.assertEqual(token.key_hash, ApiToken.hash(key))
        self.assertContains(made, f'--header "Authorization: Bearer {key}"')
        self.assertContains(made, 'Notes')
        self.assertNotContains(self.client.get(reverse('dg_connect:connect')), key)

    def test_an_area_the_person_may_not_use_is_refused(self):
        self.client.post(reverse('dg_connect:token_create'), {'name': 'Sneaky', 'scopes': ['secrets'], 'days': 0})

        self.assertFalse(ApiToken.objects.exists())

    def test_a_token_is_revoked_by_its_owner_only(self):
        mine, _key = ApiToken.issue(self.user, 'Mine', ['notes'], 0)
        bob = person('auth.view_group', username='bob', email='bob@example.com')
        theirs, _key = ApiToken.issue(bob, 'Theirs', ['notes'], 0)

        self.client.post(reverse('dg_connect:token_revoke', args=[mine.pk]))
        refused = self.client.post(reverse('dg_connect:token_revoke', args=[theirs.pk]))

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertIsNotNone(mine.revoked_at)
        self.assertEqual((refused.status_code, theirs.revoked_at), (404, None))

    def test_someone_with_no_area_gets_a_404(self):
        self.client.force_login(get_user_model().objects.create_user(username='visitor'))

        self.assertEqual(self.client.get(reverse('dg_connect:connect')).status_code, 404)


@mock.patch.dict(areas.AREAS, {'notes': NOTES, 'secrets': SECRETS}, clear=True)
class TokenRuleTests(TestCase):
    """A personal token on the MCP endpoint, which every app's API shares the ways in with."""

    @classmethod
    def setUpTestData(cls):
        cls.user = person('auth.view_group', username='anna')

    def setUp(self):
        self.token, self.key = ApiToken.issue(self.user, 'Claude Code', ['notes'], 30)

    def status(self, header: str | None = None) -> int:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=header or f'Bearer {self.key}')
        return client.post('/dg/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, format='json').status_code

    def test_a_valid_token_gets_in_and_is_marked_used(self):
        self.assertEqual(self.status(), 200)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_a_key_carries_the_prefix_and_only_its_hash_is_stored(self):
        self.assertTrue(self.key.startswith('dg_'))
        self.assertFalse(ApiToken.objects.filter(key_hash=self.key).exists())
        self.assertTrue(ApiToken.objects.filter(key_hash=ApiToken.hash(self.key)).exists())

    def test_a_key_goes_as_bearer_or_as_drf_token(self):
        for header in (f'Bearer {self.key}', f'bearer {self.key}', f'Token {self.key}'):
            with self.subTest(header=header.split()[0]):
                self.assertEqual(self.status(header), 200)

    def test_a_wrong_key_is_refused(self):
        self.assertEqual(self.status('Bearer dg_wrong'), 401)

    def test_a_revoked_or_expired_token_is_refused(self):
        ApiToken.objects.filter(pk=self.token.pk).update(revoked_at=timezone.now())
        self.assertEqual(self.status(), 401)
        ApiToken.objects.filter(pk=self.token.pk).update(revoked_at=None, expires_at=timezone.now())
        self.assertEqual(self.status(), 401)

    def test_a_token_until_revoked_has_no_expiry(self):
        token, key = ApiToken.issue(self.user, 'Integration', ['notes'], 0)

        self.assertEqual(self.status(f'Token {key}'), 200)
        self.assertIsNone(token.expires_at)

    def test_three_months_without_use_stop_a_token_even_one_never_used(self):
        ApiToken.objects.filter(pk=self.token.pk).update(last_used_at=timezone.now() - ApiToken.INACTIVE_AFTER)
        self.assertEqual(self.status(), 401)
        ApiToken.objects.filter(pk=self.token.pk).update(
            last_used_at=None, created_at=timezone.now() - ApiToken.INACTIVE_AFTER
        )
        self.assertEqual(self.status(), 401)

    def test_use_keeps_a_token_going(self):
        almost = timezone.now() - ApiToken.INACTIVE_AFTER + datetime.timedelta(days=1)
        ApiToken.objects.filter(pk=self.token.pk).update(created_at=almost - datetime.timedelta(days=300))
        ApiToken.objects.filter(pk=self.token.pk).update(last_used_at=almost)

        self.assertEqual(self.status(), 200)
        self.token.refresh_from_db()
        self.assertGreater(self.token.last_used_at, almost)

    def test_deactivating_the_user_ends_their_tokens(self):
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        self.assertEqual(self.status(), 401)

    def test_a_token_opens_only_its_areas_and_only_while_its_person_may(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.key}')
        initialize = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'}

        self.assertIn('Notes.', client.post('/dg/mcp', initialize, format='json').json()['result']['instructions'])
        self.user.user_permissions.clear()
        self.assertNotIn('Notes.', client.post('/dg/mcp', initialize, format='json').json()['result']['instructions'])

    def test_a_host_project_s_own_bearer_token_passes_by(self):
        with self.settings(DG_AUTHENTICATION_CLASSES=['datagroceries.connect.tests.test_tokens.HostBearer']):
            self.assertEqual(self.status('Bearer host-anna'), 200)


class HostBearer(BaseAuthentication):
    """A host project's own Bearer tokens, such as JWTs: `Bearer host-<username>`."""

    def authenticate(self, request):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer host-'):
            return None
        return get_user_model().objects.get(username=header.removeprefix('Bearer host-')), 'a host token'
