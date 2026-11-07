"""Tests for Markdown as every DataGroceries app shows it (datagroceries.core.markdown); the board's references are
tested with the board."""

import re
import xml.etree.ElementTree as ET

from django.template import Context, Template
from django.test import SimpleTestCase

from datagroceries.core import markdown


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

    @classmethod
    def help(cls):
        return [('!NAME!', 'Shouts the name.')]

    def resolve(self, matches):
        if 'polite' in self.context:
            return {}
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

    def test_a_reference_reads_what_the_text_belongs_to(self):
        self.assertIn('!HI!', markdown.render('Say !HI!.', context={'polite': True}))

    def test_the_writing_help_explains_markdown_and_the_references(self):
        help_html = Template('{% load dg_core %}{% markdown_help %}').render(Context())

        self.assertIn('<template id="dg-editor-help">', help_html)
        self.assertIn('**bold**', help_html)
        self.assertInHTML('<tr><td><code>!NAME!</code></td><td>Shouts the name.</td></tr>', help_html)

    def test_registering_twice_counts_once(self):
        markdown.register(Shout)

        self.assertEqual(markdown.REFERENCES.count(Shout), 1)


class DocumentTests(SimpleTestCase):
    def test_a_document_has_its_headings_for_a_table_of_contents(self):
        html, headings = markdown.render_document('# Title\n\n## Tom & Jerry\n\n### *Sub*\n\n## Tom & Jerry')

        self.assertIn('<h2 id="h-tom-jerry">Tom &amp; Jerry</h2>', html)
        self.assertEqual(
            headings,
            [
                markdown.Heading(2, 'h-tom-jerry', 'Tom & Jerry'),
                markdown.Heading(3, 'h-sub', 'Sub'),
                markdown.Heading(2, 'h-tom-jerry_1', 'Tom & Jerry'),
            ],
        )

    def test_other_text_has_no_ids_on_its_headings(self):
        self.assertIn('<h2>Plan</h2>', markdown.render('## Plan'))

    def test_raw_html_cannot_set_an_id(self):
        html, _headings = markdown.render_document('<p id="login">Hi</p>')

        self.assertNotIn('id="login"', html)

    def test_raw_html_cannot_give_a_heading_an_id_of_its_own(self):
        html, _headings = markdown.render_document('<h2 id="dg-mention-people">[]</h2>\n\n## Plan')

        self.assertNotIn('dg-mention-people', html)
        self.assertIn('<h2 id="h-plan">Plan</h2>', html)
