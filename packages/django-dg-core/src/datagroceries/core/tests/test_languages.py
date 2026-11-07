"""Tests for the language switch in the layout's header."""

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from datagroceries.core.templatetags.dg_core import dg_languages

WITHOUT_LOCALE = [name for name in settings.MIDDLEWARE if name != 'django.middleware.locale.LocaleMiddleware']


def layout() -> str:
    request = RequestFactory().get('/dg/board/?q=x')
    request.user = AnonymousUser()
    return render_to_string('dg_core/base.html', request=request)


@override_settings(LANGUAGES=[('en', 'English'), ('nl', 'Dutch')])
class LanguageSwitchTests(TestCase):
    def test_the_header_offers_each_language_by_its_own_name(self):
        page = layout()

        self.assertIn(reverse('dg_core:set_language'), page)
        self.assertIn('<input type="hidden" name="next" value="/dg/board/?q=x">', page)
        self.assertIn('value="en" lang="en"', page)
        self.assertIn('Nederlands</button>', page)

    def test_only_the_languages_the_apps_speak_too(self):
        with self.settings(LANGUAGES=[('en', 'English'), ('nl', 'Dutch'), ('fr', 'French'), ('de-at', 'German')]):
            self.assertEqual(dg_languages(), [('en', 'English'), ('nl', 'Nederlands')])

    def test_no_switch_with_one_language(self):
        with self.settings(LANGUAGES=[('en', 'English'), ('fr', 'French')]):
            self.assertEqual(dg_languages(), [])
            self.assertNotIn('set_language', layout())

    @override_settings(MIDDLEWARE=WITHOUT_LOCALE)
    def test_no_switch_when_the_project_does_not_follow_the_language(self):
        self.assertEqual(dg_languages(), [])
        self.assertNotIn(reverse('dg_core:set_language'), layout())

    def test_the_choice_is_remembered(self):
        response = self.client.post(reverse('dg_core:set_language'), {'language': 'nl', 'next': '/dg/board/'})

        self.assertRedirects(response, '/dg/board/', fetch_redirect_response=False)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'nl')
