# Changelog of django-dg-core

## 1.1.0 (2026-11-07)

Not backwards compatible, though a minor version: 1.0 was a day old and hardly anyone had it. Board and
wiki 1.1.0 need it, and 1.0 of either does not work with it.

- **Notifications are a hook.** How someone hears about a change is a subclass of
  `datagroceries.core.notifications.Notifier`, named in `DG_NOTIFIER`; the default is an email, as before.
  Not backwards compatible: `DG_NOTIFICATIONS` and `DG_SLACK_BOT_TOKEN` are gone, and with them Slack and
  the `requests` dependency. Slack is a few lines of your own; docs/integrating.md shows how. The check
  `dg.E003` now says `DG_NOTIFIER` cannot be imported, and `dg.E004` is gone.
- **A notifier gets the whole event.** `Message` has what happened (`kind`, such as `mentioned`), who did
  it (`actor`), what it is about (`subject`, and the ticket or page itself as `about`), besides the
  sentence, the link and the quote. Apps send one with `notifications.send(users, message)`.
- **The default email is written from templates** (`dg_core/notifications/`), which a project overrides
  to change how it looks: text and HTML, with the ticket or page as its subject, every email about one
  in one thread, and a last line saying why it came and where to stop.

## 1.0.0 (2026-11-07)

The first release: the one MCP endpoint for every installed DataGroceries app, the checks on every way in
(registered token packages and the project's own DRF authentication, with the `401` that points MCP
clients at their authorization server), people as a Django permission per app and one `People` class,
notifications by email and Slack with fallback, each in its person's language, @-mentions of the people
of an area, what names something of one app in another's text, what the apps' REST APIs share, DataGroceries'
own layout with its assets, a switch between the apps and a language switch, Markdown rendering and the
Markdown editor, with writing help each app adds to, and references between apps, which may be relative
to what the text belongs to (and for a page of its own, such as a wiki page, anchors on its headings for
a table of contents), attachments each app keeps in a table of its own and serves so that no file runs as
a page, English and Dutch, one URL include, and system checks. Django 5.2 LTS and 6.x, Python 3.11 and
newer.
