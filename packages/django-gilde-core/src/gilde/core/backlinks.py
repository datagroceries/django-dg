"""What names something of one app in another app's text: the wiki pages that name a ticket, shown on the
ticket. An app that keeps text registers a `Source` from its AppConfig.ready(); an app shows what names
one of its things with `find`, so neither knows the other.
"""

import dataclasses
import typing

from gilde.core.authentication import opens


@dataclasses.dataclass(frozen=True)
class Backlink:
    title: str
    url: str


@dataclasses.dataclass(frozen=True)
class Source:
    """Text of the area `scope`. `find(name)` gives the places in it that name `name` as a word, such as
    "T-123", outside code; `label` says what they are, as "Wiki pages"."""

    scope: str
    label: str
    find: typing.Callable[[str], list[Backlink]]


SOURCES: list[Source] = []


def register(source: Source):
    if source not in SOURCES:
        SOURCES.append(source)


def find(request, name: str) -> list[tuple[Source, list[Backlink]]]:
    """The places that name `name`, in the areas the request reaches (its user may use them, and its token,
    if any, opens them), by source; sources without any are left out."""
    found = [(source, source.find(name)) for source in SOURCES if opens(request, source.scope)]
    return [(source, places) for source, places in found if places]
