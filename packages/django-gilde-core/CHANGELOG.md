# Changelog of django-gilde-core

## 1.0.0 (unreleased)

The first release: the one MCP endpoint for every installed Gilde app, the checks on every way in
(registered token packages and the project's own DRF authentication, with the `401` that points MCP
clients at their authorization server), people as a Django permission per app and one `People` class,
notifications by email and Slack with fallback, each in its person's language, @-mentions of the people
of an area, Gilde's own layout with its assets and a language switch, Markdown rendering and the Markdown
editor, with writing help each app adds to, and references between apps, which may be relative to what
the text belongs to (and for a page of its own, such as a wiki page, anchors on its headings for a table
of contents), attachments each app keeps in a table of its own and serves so that no file runs as a page,
English and Dutch, one URL include, and system checks. Django 5.2 LTS and 6.x, Python 3.11 and newer.
