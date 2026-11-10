# The board, inside

How django-dg-board is built and why, for contributors and agents working on it. What it offers and
how to install it are in its [README](../packages/django-dg-board/README.md).

## Principles of the board

The board is opinionated: it does each thing one way, the right one, for everyone. Fewer ways means
less to build, test and keep working, and a board that behaves the same for the whole team.

- **No options.** Choose the right solution and build only that, without a per-user or per-browser
  switch to have it another way. Where people disagree, decide once, for everyone; when the decision
  proves wrong, change it for everyone. Remembering where someone was, such as their last filters or a
  folded lane, is not an option in this sense: it changes nothing about how the board works.
- **Every part of a page has one job.** Above the lanes go filters and nothing else. That bar is
  crowded already, on a phone above all, so even a new filter has to earn its place there; something
  of another kind goes where its kind lives.
- **Settings**, if one ever proves unavoidable, live together in one place for settings, never among
  the filters.
- **Be sparing with features.** When everyone adds their own wish in their own way, the board becomes
  an unmaintainable Christmas tree within weeks. A new feature answers a need the whole team shares, is
  built the way the board already works, and is agreed with the people who maintain the board before
  it is built. An agent asked for one checks it against these principles first, and says so when it
  does not fit.

## Requirements

### Boards and groups

- A kanban view only, with drag and drop, and a **+** between cards to create a ticket right there.
- Any number of groups: per team, or for any other reason. Each group defines its own columns in the
  UI; a column's category (to do / in progress / done) is what "open" means across groups.
- Switch groups with tabs. Filter on assignee, creator and label (all multi-select), on text, on
  the place among parents and subtasks: all tickets, top level (no parent) or parents only, and on
  one ticket and everything under it. Across all groups, the lanes are the three categories.
- A ticket can move to another group; its key never changes.

### Tickets

- Fields are fixed in code: a new one is a code change and a migration.
- Exactly one creator, and zero or one assignee.
- Size: hours, days, weeks, months, unknown (can't tell), or empty (not estimated yet).
- Any number of free labels.
- Blocked, with a history: switching it on or off takes a comment that says why.
- Relations: duplicate of, blocks, relates to, and parent/child, with at most one parent. That
  replaces epics and sub-items.
- A Markdown description in a robust editor (EasyMDE).
- A screenshot is attached by dropping or pasting it anywhere on the ticket page.
- Comments, with one level of replies, both written and edited in the same Markdown editor.
- One activity feed with every change, comment and relation.
- Everything is edited on the ticket page itself.
- A short URL with the key: `dg/board/T-123/`. One prefix for all groups.

### Integrations

- GitHub: a ticket links to the commits, branches and PRs that mention its key.
- Notifications to watchers, by email or the project's own notifier. Creator, assignee, commenters and @-mentioned people
  watch automatically, and anyone can toggle it.
- AI agents read and write tickets through the REST API and the MCP tools, as the person who connected them.

### Scope

- An app of its own that imports only from `datagroceries.core`, so any Django project can install it.

## How it works

**Models.** `Group` → `Column` (with a category) → `Ticket`. A ticket's group is its column's group,
and its key is `DG_BOARD_KEY_PREFIX` plus its id. `Relation` is one directed table (source, type,
target), shown from both sides ("child of", "blocked by"). A conditional unique constraint enforces
the single parent, and `Relation.clean` refuses loops in `parent_of` and `blocks`. `Comment.parent`
holds replies, and `Comment.sets_blocked` marks the comments that switched blocked. `Attachment`
(on core's `attachments.Attachment`) is a file in the default storage, served through the board to the people on it only, so that storage
must not publish it at an address of its own; only known image types are shown inline. Its address ends in its slugified file name (`attachments/143/screenshot.png`),
because the Markdown editor inserts an upload as an image only when the URL ends in an image
extension; the address without the name leads to the file too.

**Behaviour worth knowing.**

- A `blocks` relation only counts while the blocker is not done.
- Changing the group puts the ticket in the new group's first column of the same category.
- A ticket can be deleted on its page, for a mistake or a duplicate; its comments, relations, watchers,
  code links and attachments go with it. A ticket decided against goes to Won't do instead, and keeps
  its history. The attachment files are deleted from the storage once the ticket is gone.
- A subtask's card links to its parent, and a parent's card counts its done subtasks. A label on a
  card filters the board on that label.
- Only its author can edit a comment or reply, which then shows as edited (a `~` record in its
  history). Only the people the edit newly @-mentions hear about it; the watchers had the first
  version.
- A group can be deleted once it holds no tickets; its columns go with it. The activity feed still
  names them, from their last history record.
- A group's settings (name, order, done days, columns) open from Group settings on its own board, and
  "+ New group" beside the group tabs makes one; there is no separate list of groups, as the tabs are one.
- A ticket entering a done column gets `closed_at`. Done tickets leave the board after their group's
  `done_days` (14 unless set otherwise on the group's page), but their page stays. Across all groups
  each ticket follows its own group's (`Ticket.objects.on_board()`). One value per group, set by
  whoever looks after that board, so teams need not agree on one.
- All tickets share one order, Jira's "rank": each column shows its own tickets in it, and so do the
  lists of related tickets and subtasks on a ticket page. Dragging a card on the board or a row in
  such a list therefore moves the ticket in both. A drop sends the ticket it landed above (or, at the
  end of a list, below), not an index, so it stays right on a filtered board. Ranks leave gaps, so a
  move changes one rank, and a new place alone writes no history. A status change puts the ticket at
  the top of its new column, and a new ticket goes to the bottom of its column.
- Title and description edits carry a fingerprint of the text they started from. If somebody changed
  that text meanwhile, the save is refused and names them; changes to other fields never get in the
  way.
- A ticket key in any Markdown text links to that ticket, with its title on hover (`ticket_links.py`, a
  reference in core's Markdown, so in other DataGroceries apps too), and an `@jasper` that names a colleague shows
  as a mention, with their name on hover (core's `mentions`); keys and handles that name nobody, or sit in
  code, stay text.
- On the board: a new ticket starts in a column, from the "+" at its head (`c` takes the first
  column's); a "+" between cards opens a title field in place (Enter adds, Esc stops). The search
  filters the board as it is typed; Enter on a key (`T-12`, or its number alone) or a
  unique word opens that ticket, and `/` goes to the search. A board's address with a search only
  filters, so a reload or Back from the ticket shows the board, not the ticket again. The board reopens with each viewer's last group and filters, kept in their session; a
  search is a one-off and changes nothing of that.
- Cards are dragged between columns; on a touchscreen only after a moment's press, so scrolling does
  not move them.
- A click on a card's assignee, or on the faint person-plus of a card without one, opens the same
  assignee picker as on the ticket page, and a pick saves at once (`card_assignee.js`). The board has one
  picker for all its cards, so cards the live search brings in work too. A card assigned to someone else
  stays on a board filtered on assignee until the next load.
- A lane folds into a narrow strip from the button at its head, and a click on the strip opens it.
  A card dropped on the strip goes to the bottom of that column. Folded lanes are remembered per
  browser, in `localStorage`: by column on a group's board, by category on all groups.
- Open on board, beside the heading of a ticket's subtasks, and a parent card's count of
  done subtasks open the main board on that ticket and everything under it, subtasks of subtasks
  included, so its other filters can narrow them further. It opens on the ticket's own group; the All
  groups tab adds the subtasks in other groups. The board remembers it like any filter, shows it as
  "Under T-123", and its cross takes it off.
- A click on a card, apart from its labels and other links, opens the ticket's page. The eye that shows
  on a card or a related ticket's row while it is hovered opens a quick view instead: the ticket in
  brief in a panel on the right (`peek.js`, `_peek.html` from `<key>/peek/`), beside a page that stays
  usable, so the next eye can be clicked straight away. It only shows, and copies a link; Open ticket
  goes to the page, where everything is changed. A related ticket in the panel opens there too, and the
  same eye again, a click beside the panel or Esc closes it. A screen without hover, such as a phone's, has no eye: there
  the panel would cover the page anyway.
- One search, `Ticket.objects.search()`, sits behind the board, the relation picker and the API: the
  ticket a key names (`T-831`, or `831`) first, then title matches, then
  description matches. Change what a search finds there, and every one of them follows.
- History is `django-simple-history` on groups, columns, tickets (with their labels), relations and
  comments. The activity feed turns it into sentences.
- What both the pages and the API do to a ticket (create, move, assign, block, comment) lives in
  `operations.py`, so both follow the same rules and notify the same people.
- What someone may do in a group (read, comment, write, manage) is asked in one place, `access.py`, which
  asks the project's `People.may`. Every view, form, API call and MCP tool goes through it: a ticket is
  fetched with `access.ticket()` or from `access.tickets()`, never `Ticket.objects` alone, and a change
  calls `access.require()` first. A related ticket the viewer may not read is marked `hidden` and shown
  as such. A new view does the same.

