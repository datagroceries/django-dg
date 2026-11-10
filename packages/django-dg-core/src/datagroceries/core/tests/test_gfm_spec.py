"""The examples of the GitHub Flavored Markdown spec (fixtures/gfm_spec.txt, version 0.29-gfm, from
github/cmark-gfm, CC-BY-SA 4.0), through the parser of datagroceries.core.markdown: the HTML it reads
Markdown into, before the line breaks of a comment, the references and sanitising."""

import pathlib
import re

from django.test import SimpleTestCase

from datagroceries.core import markdown

SPEC = pathlib.Path(__file__).parent / 'fixtures' / 'gfm_spec.txt'
FENCE = '`' * 32
# The examples whose HTML differs, and why; the test fails when one of them comes out as the spec says.
KNOWN = {
    **dict.fromkeys(
        (398, 426, 434, 435, 436, 473, 474, 475, 477),
        'Strong emphasis inside strong emphasis stays nested, as CommonMark 0.31 has it: the spec is of 0.29.',
    ),
    **dict.fromkeys(
        (279, 280), 'Task lists carry the classes GitHub.com gives them too (task-list-item, contains-task-list).'
    ),
    **dict.fromkeys(
        (616, 619, 620),
        "Bare addresses become links everywhere, as on GitHub.com: these are CommonMark's examples without "
        'the autolink extension.',
    ),
    628: 'An ftp:// address stays text: the autolink plugin knows http(s) and www. only.',
    631: 'An email address with an underscore before the @ links from the underscore on (the autolink plugin).',
    652: 'Disallowed raw HTML stays in, as nh3 drops those tags anyway, and more.',
}


def examples():
    """(number, section, Markdown, HTML) of each example, with the spec's → for a tab."""
    section, lines, index, number = '', SPEC.read_text(encoding='utf-8').split('\n'), 0, 0
    while index < len(lines):
        line = lines[index]
        if line.startswith('#'):
            section = line.lstrip('#').strip()
        if line.startswith(f'{FENCE} example'):
            number += 1
            end = lines.index('.', index)
            close = next(at for at in range(end, len(lines)) if lines[at].startswith(FENCE))
            source, html = '\n'.join(lines[index + 1 : end]), '\n'.join(lines[end + 1 : close])
            yield number, section, f'{source}\n' if source else '', f'{html}\n' if html else ''
            index = close
        index += 1


def parsed(source: str) -> str:
    parser = markdown._parser(breaks=False)
    tokens = parser.parse(source.replace('→', '\t'))
    markdown._as_github(tokens)
    return parser.renderer.render(tokens, parser.options, {})


def same(html: str) -> str:
    """HTML as the spec's tests compare it: without the white space between one tag and the next."""
    return re.sub(r'>\s+<', '><', html.replace('→', '\t')).strip()


class SpecTests(SimpleTestCase):
    def test_every_example_reads_as_the_spec_says_or_differs_for_a_known_reason(self):
        found = list(examples())
        self.assertEqual(len(found), 672)
        for number, section, source, html in found:
            with self.subTest(number=number, section=section):
                if number in KNOWN:
                    self.assertNotEqual(same(parsed(source)), same(html), f'No longer differs: {KNOWN[number]}')
                else:
                    self.assertEqual(same(parsed(source)), same(html))
