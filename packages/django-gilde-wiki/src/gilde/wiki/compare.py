"""Two versions of a page's text side by side: the lines that changed, with the words that changed in them
marked, and a few unchanged lines around them; longer unchanged stretches are folded away."""

import dataclasses
import difflib
import re

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

# Unchanged lines shown before and after a change.
CONTEXT = 3
# How alike two lines must be to show as one changed line, and the most pairs of lines weighed for it.
ALIKE = 0.6
MAX_COMPARED = 2500
WORD_RE = re.compile(r'\s+|\w+|[^\w\s]')


@dataclasses.dataclass
class Row:
    """A line of each version, side by side; `kind` is "same", "changed", "removed", "added", or "folded"
    for `folded` unchanged lines left out."""

    kind: str
    left: SafeString | None = None
    left_number: int | None = None
    right: SafeString | None = None
    right_number: int | None = None
    folded: int = 0


def side_by_side(before: str, after: str) -> list[Row]:
    old, new = before.splitlines(), after.splitlines()
    rows = []
    for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(
        None, old, new, autojunk=False
    ).get_opcodes():
        if tag == 'equal':
            rows += [
                Row('same', escape(old[i]), i + 1, escape(new[j]), j + 1)
                for i, j in zip(range(old_start, old_end), range(new_start, new_end), strict=True)
            ]
            continue
        # A changed stretch: each line beside the one most like it, the words that changed marked; the
        # lines like none on the other side stand alone.
        for i, j in _pairs(old, new, range(old_start, old_end), range(new_start, new_end)):
            if i is not None and j is not None:
                rows.append(Row('changed', *_words(old[i], new[j], i + 1, j + 1)))
            elif i is not None:
                rows.append(Row('removed', mark_safe(f'<del>{escape(old[i])}</del>'), i + 1))  # noqa: S308 - escaped
            else:
                rows.append(Row('added', right=mark_safe(f'<ins>{escape(new[j])}</ins>'), right_number=j + 1))  # noqa: S308 - escaped
    return _fold(rows)


def _pairs(old: list[str], new: list[str], olds: range, news: range):
    """(old index, new index) for the lines `olds` and `news` of a changed stretch, in order: the most alike
    pair, and so on before and after it, as difflib.Differ pairs them; None where a line has no like."""
    best, pair = ALIKE, None
    if len(olds) * len(news) <= MAX_COMPARED:
        matcher = difflib.SequenceMatcher(autojunk=False)
        for j in news:
            matcher.set_seq2(new[j])
            for i in olds:
                matcher.set_seq1(old[i])
                if matcher.real_quick_ratio() > best and matcher.quick_ratio() > best and matcher.ratio() > best:
                    best, pair = matcher.ratio(), (i, j)
    if pair is None:
        yield from ((i, None) for i in olds)
        yield from ((None, j) for j in news)
        return
    i, j = pair
    yield from _pairs(old, new, range(olds.start, i), range(news.start, j))
    yield i, j
    yield from _pairs(old, new, range(i + 1, olds.stop), range(j + 1, news.stop))


def _words(old: str, new: str, old_number: int, new_number: int) -> tuple:
    old_words, new_words = WORD_RE.findall(old), WORD_RE.findall(new)
    left, right = [], []
    for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(
        None, old_words, new_words, autojunk=False
    ).get_opcodes():
        removed = escape(''.join(old_words[old_start:old_end]))
        added = escape(''.join(new_words[new_start:new_end]))
        if tag == 'equal':
            left.append(removed)
            right.append(added)
            continue
        if removed:
            left.append(f'<del>{removed}</del>')
        if added:
            right.append(f'<ins>{added}</ins>')
    # Every piece is escaped above.
    return mark_safe(''.join(left)), old_number, mark_safe(''.join(right)), new_number  # noqa: S308


def _fold(rows: list[Row]) -> list[Row]:
    shown = set()
    for index, row in enumerate(rows):
        if row.kind != 'same':
            shown.update(range(index - CONTEXT, index + CONTEXT + 1))
    result, folded = [], 0
    for index, row in enumerate(rows):
        if row.kind == 'same' and index not in shown:
            folded += 1
            continue
        if folded:
            result.append(Row('folded', folded=folded))
            folded = 0
        result.append(row)
    if folded:
        result.append(Row('folded', folded=folded))
    return result
