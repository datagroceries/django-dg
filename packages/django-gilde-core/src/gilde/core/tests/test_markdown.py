"""Tests for Markdown as every Gilde app shows it (gilde.core.markdown); the board's references are tested
with the board."""

import re
import xml.etree.ElementTree as ET

from django.test import SimpleTestCase

from gilde.core import markdown


class RenderTests(SimpleTestCase):
    def test_raw_html_is_stripped(self):
        html = markdown.render('Hi <script>alert(1)</script> <img src=x onerror=alert(1)>')

        self.assertNotIn('<script', html)
        self.assertNotIn('onerror', html)

    def test_a_bare_url_becomes_a_link(self):
        self.assertIn('<a href="https://sentry.io/x"', markdown.render('See https://sentry.io/x'))

    def test_a_list_right_under_a_line_is_a_list_as_on_github(self):
        html = markdown.render('Steps:\n- one\n- two\n\nThen:\n1. first')

        self.assertIn('<p>Steps:</p>\n<ul>\n<li>one</li>\n<li>two</li>\n</ul>', html)
        self.assertIn('<ol>\n<li>first</li>\n</ol>', html)

    def test_an_item_indented_by_two_spaces_is_nested_as_on_github(self):
        html = markdown.render('- one\n  - sub\n    - deeper\n- two')

        self.assertIn('<li>one<ul>\n<li>sub<ul>\n<li>deeper</li>', html)
        self.assertIn('</ul>\n</li>\n<li>two</li>', html)

    def test_a_dash_in_code_stays_code(self):
        html = markdown.render('Run:\n```\nls\n- not an item\n```')

        self.assertIn('<pre><code>ls\n- not an item\n</code></pre>', html)
        self.assertNotIn('<li>', html)

    def test_a_task_list_item_shows_a_checkbox_as_in_the_preview(self):
        html = markdown.render('Todo:\n- [ ] open\n- [x] done')

        self.assertInHTML('<li class="task-list-item"><input type="checkbox" disabled> open</li>', html)
        self.assertInHTML('<li class="task-list-item"><input type="checkbox" disabled checked> done</li>', html)

    def test_a_raw_input_can_only_be_a_disabled_checkbox(self):
        html = markdown.render('<input type="text" value="x" onfocus="alert(1)" autofocus>')

        self.assertInHTML('<input type="checkbox" disabled>', html)
        self.assertNotIn('text', html)
        self.assertNotIn('onfocus', html)


class Shout(markdown.Reference):
    """An app's reference, for the tests: a word in capitals between asterisks, which here are bangs."""

    name = 'shouts'
    pattern = re.compile(r'!([A-Z]+)!')
    classes = {'strong': {'shout'}}  # noqa: RUF012

    def resolve(self, matches):
        return {match: match.strip('!') for match in matches if match != '!NOBODY!'}

    def element(self, match, found):
        made = ET.Element('strong', {'class': 'shout'})
        made.text = found
        return made


class ReferenceTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(markdown.REFERENCES.remove, Shout)
        markdown.register(Shout)

    def test_a_registered_reference_marks_up_what_it_finds_and_keeps_its_class(self):
        html = markdown.render('Say !HI! to !NOBODY!, but not in `!CODE!`.')

        self.assertIn('<strong class="shout">HI</strong>', html)
        self.assertIn('!NOBODY!', html)
        self.assertIn('<code>!CODE!</code>', html)

    def test_a_public_page_leaves_references_as_text(self):
        html = markdown.render('Say !HI!.', references=False)

        self.assertIn('Say !HI!.', html)

    def test_registering_twice_counts_once(self):
        markdown.register(Shout)

        self.assertEqual(markdown.REFERENCES.count(Shout), 1)
