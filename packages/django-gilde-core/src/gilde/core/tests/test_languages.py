"""Tests for the language switch in the layout's header."""

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from gilde.core.templatetags.gilde_core import gilde_languages

WITHOUT_LOCALE = [name for name in settings.MIDDLEWARE if name != 'django.middleware.locale.LocaleMiddleware']


def layout() -> str:
    request = RequestFactory().get('/gilde/board/?q=x')
    request.user = AnonymousUser()
    return render_to_string('gilde_core/base.html', request=request)


@override_settings(LANGUAGES=[('en', 'English'), ('nl', 'Dutch')])
class LanguageSwitchTests(TestCase):
    def test_the_header_offers_each_language_by_its_own_name(self):
        page = layout()

        self.assertIn(reverse('gilde_core:set_language'), page)
        self.assertIn('<input type="hidden" name="next" value="/gilde/board/?q=x">', page)
        self.assertIn('value="en" lang="en"', page)
        self.assertIn('Nederlands</button>', page)

    def test_only_the_languages_gilde_speaks_too(self):
        with self.settings(LANGUAGES=[('en', 'English'), ('nl', 'Dutch'), ('fr', 'French'), ('de-at', 'German')]):
            self.assertEqual(gilde_languages(), [('en', 'English'), ('nl', 'Nederlands')])

    def test_no_switch_with_one_language(self):
        with self.settings(LANGUAGES=[('en', 'English'), ('fr', 'French')]):
            self.assertEqual(gilde_languages(), [])
            self.assertNotIn('set_language', layout())

    @override_settings(MIDDLEWARE=WITHOUT_LOCALE)
    def test_no_switch_when_the_project_does_not_follow_the_language(self):
        self.assertEqual(gilde_languages(), [])
        self.assertNotIn(reverse('gilde_core:set_language'), layout())

    def test_the_choice_is_remembered(self):
        response = self.client.post(reverse('gilde_core:set_language'), {'language': 'nl', 'next': '/gilde/board/'})

        self.assertRedirects(response, '/gilde/board/', fetch_redirect_response=False)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'nl')
