# The wiki, inside

How django-dg-wiki is built and why, for contributors and agents working on it. What it offers and
how to install it are in its [README](../packages/django-dg-wiki/README.md).

## Principles of the wiki

The wiki follows the board's principles ([board.md](board.md#principles-of-the-board)): no options, every
part of a page one job, sparing with features. On top of those:

- **One tree.** There are no spaces, books or folders apart from pages: a page with pages under it is
  all of those. Its text is what elsewhere is an index page.
- **An address is a page's place.** A page lives at the slugs of its ancestors and its own
  (`dg/wiki/engineering/deploying/`). Renaming or moving changes it, and the old address keeps leading
  to the page, so a link never breaks.
- **Links follow.** A link written in the wiki names a page as people do, and is rewritten when that
  page, or the page the link is in, gets another address.
- **Nothing is lost.** Every save is a version; bringing an old one back is a new version, and a save
  made on top of someone else's is refused, naming them.

## Requirements

### Pages

- Pages in Markdown, written in core's editor, with images pasted or dropped into the text and files
  beside the page.
- One tree, ordered by dragging in the sidebar or chosen with Move; a page with pages under it cannot be
  deleted.
- A table of contents beside a long page, from its headings of levels 2 to 4.
- Every version kept, with who made it and through which agent; two versions side by side, the changed
  words marked, and an earlier one brought back.
- Comments with one level of replies, @-mentions and watchers, as on the board.
- Search through every title and text.
- A language per page, and translations beside it that link to each other.
- A page, a page with all under it, or the whole wiki downloaded as Markdown.

### Integrations

- `[[...]]` links in every DataGroceries app's Markdown, so a ticket can link to a page.
- A ticket lists the wiki pages that name its key.
- AI agents read and write pages through the REST API and the MCP tools, as the person who connected them.

### Scope

- An app of its own that imports only from `datagroceries.core`, so any Django project can install it.

## How it works

**Models.** `Page` has a `parent`, a `position` among the pages beside it, a `slug` from its title,
unique among them, and a `path`, the slugs of its ancestors and its own, unique in the wiki. `Page.save`
keeps them right: a new title or parent gives a new path to the page and everything under it, and each
old path becomes a `FormerPath`, which leads to the page until a page takes that address. The wiki's own
pages are under `-/` (`dg/wiki/-/search/`, `.../deploying/-/edit/`), which no page's address can be, as
a slug never starts with a dash. `Link` keeps the links in a page's text, by the address they name and
the page that is. `Comment`, `Watcher` and `Attachment` (on core's `attachments.Attachment`) are the
wiki's own, as the board has its own. `Page.language` and `Page.original` make translations: every
translation names the same original.

**Links** (`links.py`). A link names a page by its address, written in titles or slugs:
`[[Deploying/Rollback]]` and `[[deploying/rollback]]` are the same. It is found as a browser finds a
relative address. Every page is also a folder of the pages under it, as its address ends in a `/`, so a
link starts from the page it is in. On the page Engineering (`/engineering/`):

- `[[Deploying]]`, or `[[./Deploying]]`: the page Deploying under Engineering. `[[Deploying/Rollback]]` is
  further down.
- `[[../Sales]]`: the page Sales beside Engineering; each `../` goes one level up.
- `[[/Sales/Q4]]`: from the top of the wiki. Outside a page, as in a ticket, only these are links, as
  nothing gives the others a place to start from; they stay text.
- `[[Deploying|how we ship]]`: with words of your own; without them a link shows the page's title.
- Nothing else is looked for: `[[Deploying]]` on Sales is `/sales/deploying`, never a Deploying elsewhere in
  the tree, so a link means one address only, and a page made elsewhere never changes where it goes.
- A `/` at the end changes nothing: `[[Sales/]]` is `[[Sales]]`. A former address finds its page.
- A link to a page not there yet shows dashed and red, and leads to where the page can be started, with
  the title from the link: at the address the link names, so only a title with the same slug will do, and
  only once the pages above it are there (`StartPageForm`, `views._missing`). A link with no name to show,
  as `[[..]]` with no page above, stays text.

The rule was chosen over two others (G-61): a page with pages under it as a folder's index and one without
as a file, where `[[Platform]]` would be the page beside it but a link would change meaning when a page
got its first page under it; and every page a file beside a folder of its name, where a link to a page
under it would repeat the page's own name. Links mostly go to the pages under a page, so those are short.

The editor's writing help (the "?") explains these in a part of its own, wherever the wiki is installed,
so in a ticket's editor too: `PageLinks.help_heading` and `PageLinks.help`.

`PageLinks` is a reference in core's Markdown registry, so every app renders the links while the wiki is
installed. The page it renders in comes in the render's `context` (`{'wiki_page': page, 'scope':
'wiki'}`). On save, `links.record` keeps the page's links; after an address changes, `links.follow`
rewrites the links to the moved pages, and the relative links in them, in the way each was written (titles
or slugs, relative or from the top), and `links.refresh` looks up again the links that name an address a
page now has. The pages so rewritten are saved, each with a version of its own. Links in code are left alone.

**Behaviour worth knowing.**

- A new page starts from its title alone and opens in the editor. An address that is no page offers to
  start one there.
- Dragging in the tree posts the page, its new parent and the page it now sits before; the server answers
  with the tree. Reordering writes no version: a page's order is not kept in its history, its parent is.
- Saving carries a fingerprint of the title and text the editor started from; when somebody saved
  meanwhile, the save is refused, naming them, and the text stays in the editor. The API does the same
  with the version a change started from (409).
- Bringing a version back takes its title and text, not its place, as a new version that notes which one
  it restored (`restored_from` on the history record).
- Two versions show as their lines side by side, each changed line beside the line most like it on the
  other side (`compare.py`, as `difflib.Differ` pairs them), the changed words marked, and unchanged
  stretches folded.
- Watchers hear about new comments, not every save: a page is written in many small saves, which its
  history keeps. The creator, whoever writes or comments, and whoever is @-mentioned in the text or a
  comment watch of themselves.
- Search (`search.py`) is `icontains` on every word, so it runs on any database; pages with the words in
  their title come first. Its text around the first word leaves Markdown's marks out.
- A translation goes beside its page, starting from its text. A translation older than the latest change
  to its original says so. Deleting the original makes its first translation the original of the others.
- An export (`export.py`) is one Markdown file, or a zip of files at their addresses with their images
  beside them; links between the files in it become relative links, other links the wiki's address.
- The ticket's list of wiki pages comes through core's `backlinks` registry: the wiki registers its pages
  as a source (`search.naming`), the board asks what names a ticket. It shows only to people, and tokens,
  that reach the wiki.
- What both the pages and the API do to a page lives in `operations.py`, so both follow the same rules
  and notify the same people; `versions.py` describes the versions for both.
- What someone may do on a page (read, comment, write) is asked in one place, `access.py`, which asks the
  project's `People.may` about the page, or `TOP` for the top. Reading needs read on every page above it
  too. Every view, form, API call and MCP tool goes through it: a page is fetched with `access.page()` or
  from `access.pages()`, never `Page.objects` alone, and each operation calls `access.require()` first.
  `access` remembers the answers for the request, works out once which pages someone may not read
  (`access.hidden()`, skipping a branch they may not read), and asks nothing when the project's `People`
  leaves `may` as it is. A new view does the same.
