"""The wiki's area for agents: its token scope, and in time its MCP tools. Registered with gilde.core in
WikiConfig.ready()."""

from django.utils.translation import gettext_lazy as _

from gilde.core.areas import Area
from gilde.wiki.conf import SCOPE

AREA = Area(
    scope=SCOPE,
    label=_('Wiki'),
    permission='gilde_wiki.use',
    instructions="The wiki is the team's own knowledge: pages in Markdown, in one tree.",
)
