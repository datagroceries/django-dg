# Changelog of django-dg-board

## Unreleased

Needs the next django-dg-core, for `People.may`.

- **Access per group**, as the project decides in `People.may`: who may read, comment, write or manage
  each group, on the pages and in the API and MCP tools alike (`access.py`). Who may not read a group
  does not see its tickets anywhere, a relation to one shows as a ticket they cannot see, and they
  neither hear about it nor can be assigned it. Controls show only to whoever may use them. By default
  nothing changes: whoever may use the board may do everything.
- An @-mention on a ticket of someone who may not read it is muted, in the text and in the editor.

## 1.1.0 (2026-11-07)

Needs django-dg-core 1.1.0.

- Notifications go through core's new notifier, which a project can take over entirely; each says what
  happened (`assigned`, `mentioned`, `commented`, `blocked`, `unblocked` or `done`) and which ticket it
  is about. By default an email with the ticket as its subject, in one thread per ticket.
- **Breaking:** `DG_BOARD_DISPLAY_TIMEZONE` is gone. The pages show times in Django's current timezone,
  as the wiki and the project's own pages do: `TIME_ZONE`, or each person's own when the project
  activates it in a middleware. A project that set it sets `TIME_ZONE` instead.

## 1.0.0 (2026-11-07)

The first release: the kanban board with groups and their own columns, tickets with parents, relations,
blockers, labels, sizes, comments and attachments, @-mentions and watchers, the activity feed, links to
GitHub code, what names a ticket in the other DataGroceries apps (such as wiki pages), a REST API and MCP tools
for working on tickets as on the pages, and English and Dutch. It started as Eddy Board, Eddy Grid's own
tracker.
