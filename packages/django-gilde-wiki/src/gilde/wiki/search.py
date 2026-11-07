"""Finding pages: those whose title or text holds every word searched for, those with the words in their
title first, then the most recently changed; each with the stretch of text where a word first appears.

Plain `icontains` on every database Django supports, which is quick enough for a team's wiki of some
thousands of pages; the pages and, in time, the MCP tools both search with it.
"""

import dataclasses
import re

from django.db.models import Q
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from gilde.wiki.models import Page

MAX_WORDS = 10
MAX_HITS = 50
# How much text a hit shows around the first word found.
SNIPPET_BEFORE = 60
SNIPPET_LENGTH = 200
# Markdown's marks, left out of a snippet: those that start a line (headings, quotes, list items and their
# checkboxes), and those within it (emphasis, code, a wiki link's brackets and address, a link's address).
LINE_MARKS_RE = re.compile(r'(?m)^[ \t]*(?:#+|>|(?:[-*+]|\d+\.)(?:[ \t]+\[[ xX]\])?)[ \t]+')
INLINE_MARKS_RE = re.compile(r'[*_`~]+|\[\[(?:[^\]|\n]*\|)?|\]\]|\]\([^)\n]*\)|!?\[')


@dataclasses.dataclass
class Hit:
    page: Page
    snippet: SafeString


def words_of(query: str) -> list[str]:
    return query.split()[:MAX_WORDS]


def search(query: str) -> list[Hit]:
    """The pages that hold every word of `query`, the best first."""
    words = words_of(query)
    if not words:
        return []
    pages = Page.objects.all()
    for word in words:
        pages = pages.filter(Q(title__icontains=word) | Q(body__icontains=word))
    found = list(pages.order_by('-updated_at')[: MAX_HITS * 4])
    found.sort(key=lambda page: -sum(word.lower() in page.title.lower() for word in words))
    return [Hit(page, snippet(page.body, words)) for page in found[:MAX_HITS]]


def snippet(text: str, words: list[str]) -> SafeString:
    """The text around the first of `words` in it, without Markdown's marks, the words marked."""
    plain = ' '.join(INLINE_MARKS_RE.sub('', LINE_MARKS_RE.sub('', text)).split())
    pattern = re.compile('|'.join(re.escape(word) for word in sorted(words, key=len, reverse=True)), re.IGNORECASE)
    first = pattern.search(plain)
    start = max(0, first.start() - SNIPPET_BEFORE) if first else 0
    if start:
        # From the start of a word.
        start = plain.find(' ', start) + 1 or start
    piece = plain[start : start + SNIPPET_LENGTH]
    marked, last = [], 0
    for match in pattern.finditer(piece):
        marked += [escape(piece[last : match.start()]), f'<mark>{escape(match[0])}</mark>']
        last = match.end()
    marked.append(escape(piece[last:]))
    ellipsis_before = '…' if start else ''
    ellipsis_after = '…' if start + SNIPPET_LENGTH < len(plain) else ''
    # Every piece is escaped above.
    return mark_safe(f'{ellipsis_before}{"".join(marked)}{ellipsis_after}')  # noqa: S308
