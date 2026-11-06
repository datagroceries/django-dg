"""Read lists the way GitHub and the editor's preview do, so a list shows as one once saved.

Python-Markdown starts a list only after an empty line, and nests one only four spaces deep. Text
written for GitHub does neither: "Steps:" followed by "- one" on the next line stays a paragraph with
dashes, and an item indented by two spaces lands at the outer level. This puts the empty line in and
deepens the indent, before Python-Markdown reads the text. Fenced code is set aside before this runs,
so it is left alone.
"""

import re

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

# A list item, indented less than an indented code block would be at the top level.
LIST_ITEM_RE = re.compile(r'^( *)(?:[-*+]|\d+\.) +\S')
NESTED_INDENT = 4


class _ListPreprocessor(Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        result = []
        # The indents of the open list levels, outermost first; empty outside a list.
        levels = []
        for line in lines:
            item = LIST_ITEM_RE.match(line)
            if item and (levels or len(item[1]) < NESTED_INDENT):
                if not levels and result and result[-1].strip():
                    result.append('')
                indent = len(item[1])
                while levels and levels[-1] > indent:
                    levels.pop()
                if not levels or indent > levels[-1]:
                    levels.append(indent)
                result.append(' ' * NESTED_INDENT * (len(levels) - 1) + line.lstrip(' '))
                continue
            if line.strip() and not line.startswith((' ', '\t')) and not (result and result[-1].strip()):
                # Unindented text after an empty line ends the list.
                levels = []
            result.append(line)
        return result


class ListExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802 - Markdown's name for it
        # After fenced_code (25) has set code blocks aside.
        md.preprocessors.register(_ListPreprocessor(md), 'github_lists', 15)
