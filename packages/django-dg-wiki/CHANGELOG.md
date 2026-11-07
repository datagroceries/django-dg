# Changelog of django-dg-wiki

## 1.1.0 (2026-11-07)

Needs django-dg-core 1.1.0.

- Notifications go through core's new notifier, which a project can take over entirely; each says what
  happened (`mentioned` or `commented`) and which page it is about. By default an email with the page as
  its subject, in one thread per page.

## 1.0.0 (2026-11-07)

The first release: pages in Markdown in one tree, at addresses that follow it, put in order by dragging,
with old addresses that keep leading to their page; links between pages, `[[Engineering/Deploying]]`, by the
end of an address, the whole of it or from the page they are in, that follow a page when it moves, also in a
ticket's text, and a ticket that lists the wiki pages naming it; every version kept, compared side by side
and brought back, and a save refused when someone saved first; images and files, comments with replies,
@-mentions and watchers; search; a language per page with translations beside it; pages downloaded as
Markdown; a REST API and MCP tools for everything the pages do but uploading and downloading files; and
English and Dutch.
