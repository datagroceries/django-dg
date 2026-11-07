"""The board's settings, and their defaults. A host project sets in its own settings what it changes:

- `DG_BOARD_NAME`: what the board is called on its pages.
- `DG_BOARD_KEY_PREFIX`: the start of every ticket's key, as in T-123.
- `DG_BOARD_DISPLAY_TIMEZONE`: the timezone the pages show times in; `TIME_ZONE` by default.
- `DG_BOARD_COLORS`: the colours of the column categories, of blocked tickets, and the accents that
  tell labels and people apart.
- `DG_BOARD_GITHUB_REPOSITORY` (`owner/name`), `DG_BOARD_GITHUB_TOKEN` and
  `DG_BOARD_GITHUB_WEBHOOK_SECRET`: the repository whose code is linked to the tickets it mentions;
  empty, nothing is linked.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy

DEFAULTS = {
    'DG_BOARD_NAME': gettext_lazy('Board'),
    'DG_BOARD_KEY_PREFIX': 'T',
    'DG_BOARD_DISPLAY_TIMEZONE': settings.TIME_ZONE,
    'DG_BOARD_COLORS': {
        'todo': '#6c757d',
        'in_progress': '#0d6efd',
        'done': '#198754',
        'blocked': '#dc3545',
        'accents': ['#0d6efd', '#198754', '#6f42c1', '#d63384', '#fd7e14', '#20c997'],
    },
    'DG_BOARD_GITHUB_REPOSITORY': '',
    'DG_BOARD_GITHUB_TOKEN': '',
    'DG_BOARD_GITHUB_WEBHOOK_SECRET': '',
}

for name, value in DEFAULTS.items():
    if not hasattr(settings, name):
        setattr(settings, name, value)

# The board's area: the scope of its tokens and MCP tools, and whose people it has (datagroceries.core.people).
SCOPE = 'board'
