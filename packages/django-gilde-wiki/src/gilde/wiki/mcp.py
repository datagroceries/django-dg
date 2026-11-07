"""The wiki's area for agents: its token scope, and its MCP tools, which run the views of its REST API
(gilde.wiki.api). Registered with gilde.core in WikiConfig.ready()."""

from django.utils.translation import gettext_lazy as _

from gilde.core.areas import Area
from gilde.core.mcp import Tool
from gilde.wiki.api import (
    PageCommentsView,
    PageCommentView,
    PageDetailView,
    PageHistoryView,
    PageListCreateView,
    PageTranslationsView,
    PageVersionView,
    PageWatchView,
)
from gilde.wiki.conf import SCOPE

PAGE = {
    'type': 'string',
    'description': 'The page, by its address ("engineering/deploying") or as a link to it would name it '
    '("Engineering/Deploying", or the end of it, "Deploying").',
}
MENTION = '@-mentioning someone by their handle (@ann) tells them about it.'
LINKS = (
    '[[Engineering/Deploying]] links to a page, [[Deploying|words]] with words of its own, [[/Engineering]] by its '
    'whole address, and [[./Rollback]] or [[../Onboarding]] from the page the link is in.'
)
PAGE_FIELDS = {
    'title': {
        'type': 'string',
        'maxLength': 255,
        'description': 'A new title gives the page a new address; links follow.',
    },
    'body': {'type': 'string', 'description': f'Markdown; replaces the whole text. {LINKS} {MENTION}'},
    'language': {
        'type': 'string',
        'description': 'The language the page is in, as a code such as "en"; empty for none.',
    },
    'parent': {
        'type': ['string', 'null'],
        'description': 'The page to put it under, named as `path` is; empty or null for the top.',
    },
}
TOOLS = (
    Tool(
        'search_pages',
        'Search the wiki',
        'With q, the pages holding every word, title matches first, each with the text around the first word. '
        'Without q, the tree of pages in order, each with its depth, from the page `under` or the top.',
        PageListCreateView,
        'GET',
        {
            'q': {'type': 'string', 'description': 'Words in the title or text.'},
            'under': {**PAGE, 'description': 'Without q: list only the pages under this one.'},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 1000, 'default': 200},
        },
    ),
    Tool(
        'get_page',
        'Read a wiki page',
        'One page in full: its text in Markdown, its version, who changed it last, the pages under it and '
        'linking to it, its translations, files, comments and watchers.',
        PageDetailView,
        'GET',
        {'path': PAGE},
        path=('path',),
    ),
    Tool(
        'create_page',
        'Create a wiki page',
        'A new page, last under its parent or at the top. Uploading files is not possible here.',
        PageListCreateView,
        'POST',
        PAGE_FIELDS,
        required=('title',),
    ),
    Tool(
        'update_page',
        'Change a wiki page',
        'Change the fields given, and only those: retitle it, rewrite it, or move it under another page or '
        'before another. Send the version get_page gave with a change to the title or text: it is refused '
        "when someone changed the page since, so nobody's work is lost.",
        PageDetailView,
        'PATCH',
        {
            'path': PAGE,
            **PAGE_FIELDS,
            'before': {
                **PAGE,
                'type': ['string', 'null'],
                'description': 'A page under the same parent to put it before.',
            },
            'version': {'type': 'integer', 'description': 'The version the change starts from, from get_page.'},
        },
        path=('path',),
    ),
    Tool(
        'delete_page',
        'Delete a wiki page',
        'Delete a page with no pages under it, and its files; its history stays.',
        PageDetailView,
        'DELETE',
        {'path': PAGE},
        path=('path',),
        destructive=True,
    ),
    Tool(
        'get_page_history',
        'List the versions of a page',
        'Every version of a page, newest first: who made it, when, through which agent, and what it changed.',
        PageHistoryView,
        'GET',
        {'path': PAGE},
        path=('path',),
    ),
    Tool(
        'get_page_version',
        'Read a version of a page',
        'The title and text of a page in one of its versions, as get_page_history lists them.',
        PageVersionView,
        'GET',
        {'path': PAGE, 'version': {'type': 'integer'}},
        path=('path', 'version'),
    ),
    Tool(
        'restore_page_version',
        'Bring back a version of a page',
        'Make the page say again what it said in that version, title and text, as a new version; nothing is lost.',
        PageVersionView,
        'POST',
        {'path': PAGE, 'version': {'type': 'integer'}},
        path=('path', 'version'),
    ),
    Tool(
        'comment_on_page',
        'Comment on a wiki page',
        "Add a comment, or a reply to one. The page's watchers and anyone @-mentioned hear about it at once.",
        PageCommentsView,
        'POST',
        {
            'path': PAGE,
            'body': {'type': 'string', 'description': f'Markdown. {MENTION}'},
            'parent': {
                'type': 'integer',
                'description': 'The id of the comment this replies to; replies go one level deep.',
            },
        },
        required=('body',),
        path=('path',),
    ),
    Tool(
        'edit_page_comment',
        'Edit a comment on a wiki page',
        "Replace the text of a comment or reply you wrote; nobody else's. Only the people it newly @-mentions "
        'hear about it, and it shows as edited.',
        PageCommentView,
        'PATCH',
        {
            'path': PAGE,
            'comment_id': {'type': 'integer', 'description': "The comment's id, as get_page shows it."},
            'body': {'type': 'string', 'description': f'The whole new text, Markdown. {MENTION}'},
        },
        required=('body',),
        path=('path', 'comment_id'),
    ),
    Tool(
        'translate_page',
        'Translate a wiki page',
        'A translation of the page into another language, beside it, starting from its text: write the '
        'translation into it with update_page.',
        PageTranslationsView,
        'POST',
        {
            'path': PAGE,
            'language': {'type': 'string', 'description': 'A language code, such as "nl", the page is not in yet.'},
            'title': {'type': 'string', 'description': 'The title in that language.'},
        },
        required=('language', 'title'),
        path=('path',),
    ),
    Tool(
        'watch_page',
        'Watch a wiki page',
        'Start watching a page, so the connected person hears about its comments.',
        PageWatchView,
        'POST',
        {'path': PAGE},
        path=('path',),
    ),
    Tool(
        'unwatch_page',
        'Stop watching a wiki page',
        'Stop watching a page.',
        PageWatchView,
        'DELETE',
        {'path': PAGE},
        path=('path',),
    ),
)
AREA = Area(
    scope=SCOPE,
    label=_('Wiki'),
    permission='gilde_wiki.use',
    instructions="The wiki is the team's own knowledge: pages in Markdown, in one tree. Search it before "
    'answering from memory about how the team works, and read a page before changing it.',
    tools=TOOLS,
)
