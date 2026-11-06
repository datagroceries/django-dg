"""The areas of the Gilde apps that agents reach: one per app, such as the board.

An app registers its area in its AppConfig.ready(). An area is a token scope, the Django permission
that lets someone use it (gilde.core.people), a sentence for the agent about it, and its MCP tools. A
token opens an area only while its user still may use it, so losing that right ends it on every token
at once.
"""

import dataclasses

from django.core.exceptions import ImproperlyConfigured

from gilde.core import people


@dataclasses.dataclass(frozen=True)
class Area:
    scope: str
    label: str
    permission: str
    instructions: str
    tools: tuple = ()


AREAS: dict[str, Area] = {}


def register(area: Area):
    if area.scope in AREAS:
        raise ImproperlyConfigured(f'The area {area.scope!r} is registered twice.')
    AREAS[area.scope] = area


def scopes_for(user) -> list[str]:
    """The scopes `user` may use now, in the order their apps registered them."""
    return [scope for scope in AREAS if people.may_use(user, scope)]
