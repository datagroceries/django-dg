"""Tests for the system checks (gilde.core.checks)."""

from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings

from gilde.core import areas, checks

NOTES = areas.Area(scope='notes', label='Notes', permission='auth.view_group', instructions='Notes.')


def ids(messages) -> list[str]:
    return [message.id for message in messages]


class CheckTests(TestCase):
    def test_the_example_project_passes(self):
        self.assertEqual(ids(checks.check_apps(None) + checks.check_templates(None) + checks.check_urls(None)), [])

    def test_a_missing_app_and_context_processor_are_named(self):
        templates = [{**settings.TEMPLATES[0], 'OPTIONS': {'context_processors': []}}]
        # Not INSTALLED_APPS itself: changing it would set the apps up again.
        with mock.patch.object(checks, 'REQUIRED_APPS', ('rest_framework', 'not_installed')):
            self.assertEqual(ids(checks.check_apps(None)), ['gilde.E001'])
        with override_settings(TEMPLATES=templates):
            self.assertEqual(ids(checks.check_templates(None)), ['gilde.E002'] * 3)

    @override_settings(LOGIN_URL='/nowhere/')
    def test_a_login_url_that_leads_nowhere_is_named(self):
        self.assertEqual(ids(checks.check_urls(None)), ['gilde.W002'])

    @mock.patch.dict(areas.AREAS, {'notes': NOTES}, clear=True)
    def test_an_app_only_superusers_may_use_is_named_until_a_group_may(self):
        self.assertEqual(ids(checks.check_people(None)), ['gilde.W003'])

        team = Group.objects.create(name='Team')
        team.permissions.add(Permission.objects.get(content_type__app_label='auth', codename='view_group'))
        self.assertEqual(ids(checks.check_people(None)), [])
