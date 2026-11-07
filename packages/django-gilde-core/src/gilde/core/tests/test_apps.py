"""The switch between the Gilde apps at the top of every page (gilde_core/base.html)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from gilde.core import areas
from gilde.core.tests import person

# Two apps, with start pages that exist in every project: core's own.
ONE = areas.Area('one', 'One', 'gilde_board.use', '', home='gilde_core:mcp', icon='kanban')
TWO = areas.Area('two', 'Two', 'gilde_wiki.use', '', home='gilde_core:javascript_catalog')
SWITCH = Template(
    '{% load gilde_core %}{% gilde_apps as found %}{% for app in found %}{{ app.label }} {{ app.current }};{% endfor %}'
)


class AppSwitchTests(TestCase):
    def render(self, user, path='/gilde/mcp'):
        request = RequestFactory().get(path)
        request.user = user
        with mock.patch.dict(areas.AREAS, {'one': ONE, 'two': TWO}, clear=True):
            return SWITCH.render(Context({'request': request}))

    def test_the_apps_a_person_may_use_the_one_shown_marked(self):
        boss = get_user_model().objects.create_superuser('boss', 'boss@example.com', 'x')

        self.assertEqual(self.render(boss), 'One True;Two False;')

    def test_one_app_is_nothing_to_switch_to(self):
        user = person('gilde_board.use', username='anna')

        self.assertEqual(self.render(user), '')
