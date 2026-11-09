"""The wiki's area for agents: its token scope, and its MCP tools, which run the views of its REST API
(datagroceries.wiki.api). Registered with datagroceries.core in WikiConfig.ready()."""

from django.utils.translation import gettext_lazy as _

from datagroceries.core.areas import Area
from datagroceries.core.mcp import Tool
from datagroceries.wiki.api import (
    PageCommentsView,
    PageCommentView,
    PageDetailView,
    PageHistoryView,
    PageListCreateView,
    PageTranslationsView,
    PageVersionView,
    PageWatchView,
    TopTextView,
)
from datagroceries.wiki.conf import SCOPE

PAGE = {
    'type': 'string',
    'description': 'The page, by its whole address, from the top, in slugs or titles ("engineering/deploying", '
    '"Engineering/Deploying"); search_pages lists them.',
}
MENTION = '@-mentioning someone by their handle (@ann) tells them about it.'
LINKS = (
    'A link to a wiki page starts in the folder it is written in, as a relative address does in a browser: on a '
    'folder, such as Engineering, [[Deploying]] is the page Deploying in it; on a page of its own in Engineering, '
    '[[Deploying]] is the page beside it, in the same folder. [[Deploying/Rollback]] goes further down, '
    '[[../Sales]] one folder up (each ../ is one level). [[/Sales/Q4]] starts from the top of the wiki, and is '
    'the only kind that works outside the wiki, as in a ticket. [[Deploying|how we ship]] links with words of '
    'its own. Nothing else is looked for: [[Deploying]] never finds a page elsewhere in the tree. A link to a '
    'page not there yet shows red, and following it starts that page.'
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
        'description': 'The folder to put it in, named as `path` is; empty or null for the top.',
    },
    'folder': {
        'type': 'boolean',
        'description': 'A folder, whose text is the index of the pages in it, or a page of its own. Only a folder '
        'has pages in it, and only one with none in it becomes a page again. Making a page a folder keeps its '
        'address and rewrites the relative links in its text, which then start from it, to name the same pages.',
    },
}
TOOLS = (
    Tool(
        'get_wiki_start',
        'Read the start page of the wiki',
        "The wiki's own text, as the top folder's: what everyone sees first, above the pages at the top. Its "
        'version, for update_wiki_start.',
        TopTextView,
        'GET',
        {},
    ),
    Tool(
        'update_wiki_start',
        'Change the start page of the wiki',
        "Replace the wiki's own text. Send the version get_wiki_start gave: it is refused when someone changed "
        "the text since, so nobody's work is lost.",
        TopTextView,
        'PATCH',
        {
            'body': {
                'type': 'string',
                'description': f'Markdown; replaces the whole text. Links start at the top. {LINKS}',
            },
            'version': {'type': 'integer', 'description': 'The version the change starts from, from get_wiki_start.'},
        },
        required=('body',),
    ),
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
        'Add a wiki page in another language',
        'A version of a page, which has a language, in another: either a new page beside it, starting from its '
        'text, which you then translate and write with update_page (give language and title), or a page that is '
        'already there in another language and linked to no others (give page). Its title must differ from the '
        "other pages' in the folder.",
        PageTranslationsView,
        'POST',
        {
            'path': PAGE,
            'language': {'type': 'string', 'description': 'A language code, such as "nl", the page is not in yet.'},
            'title': {'type': 'string', 'description': 'The title in that language.'},
            'page': {**PAGE, 'description': 'A page already there to link instead, named as `path` is.'},
        },
        path=('path',),
    ),
    Tool(
        'unlink_page_translation',
        'Unlink a wiki page from its other languages',
        'Take a page out of the versions in other languages it is one of; it stays, as a page of its own, and '
        'the others stay linked to each other.',
        PageTranslationsView,
        'DELETE',
        {'path': PAGE},
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
    permission='dg_wiki.use',
    instructions="The wiki is the team's own knowledge: pages in Markdown, in one tree. Search it before "
    'answering from memory about how the team works, and read a page before changing it.',
    tools=TOOLS,
    home='dg_wiki:home',
    icon='journal-text',
)
