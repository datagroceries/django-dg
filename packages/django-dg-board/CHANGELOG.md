# Changelog of django-dg-board

## Unreleased

- **Breaking:** `DG_BOARD_DISPLAY_TIMEZONE` is gone. The pages show times in Django's current timezone,
  as the wiki and the project's own pages do: `TIME_ZONE`, or each person's own when the project
  activates it in a middleware. A project that set it sets `TIME_ZONE` instead.

## 1.0.0 (2026-11-07)

The first release: the kanban board with groups and their own columns, tickets with parents, relations,
blockers, labels, sizes, comments and attachments, @-mentions and watchers, the activity feed, links to
GitHub code, what names a ticket in the other DataGroceries apps (such as wiki pages), a REST API and MCP tools
for working on tickets as on the pages, and English and Dutch. It started as Eddy Board, Eddy Grid's own
tracker.
