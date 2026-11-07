"""The wiki's settings, and their defaults. A host project sets in its own settings what it changes:

- `DG_WIKI_NAME`: what the wiki is called on its pages.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy

DEFAULTS = {
    'DG_WIKI_NAME': gettext_lazy('Wiki'),
}

for name, value in DEFAULTS.items():
    if not hasattr(settings, name):
        setattr(settings, name, value)

# The wiki's area: the scope of its tokens and MCP tools, and whose people it has (datagroceries.core.people).
SCOPE = 'wiki'
