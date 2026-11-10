# Changelog of django-dg-core

## 1.4.0 (2026-11-10)

Wiki 1.3.0 needs it.

- `People.suggested(area)`: whom the editor suggests after an @, by default everyone a mention reaches
  (`members`). A mention of someone it leaves out still reaches them, written by their handle.
- `may_use_required(scope, anonymous=True)` lets someone not signed in into a page when `People.may_use`
  says yes to them, which by default it does not. The header offers whoever is not signed in to sign in
  (`sign_in_url`).

## 1.3.0 (2026-11-09)

Wiki 1.2.0 needs it.

- `People.may(user, right, where)` is asked about a wiki page, or the wiki's top, as well as a board
  group; its third argument is called `where` now.
- `people.restricts()`: whether the project's `People` overrides `may`, so an app can skip working out
  who may see what when nothing is restricted.
- The editor's writing help shows all of itself, no longer in a box of its own height that hid the parts
  below without a scrollbar on a Mac, and opens under the editor's buttons rather than between the text
  and them.
- A reference may give its rows in the editor's writing help a part of their own, under its
  `help_heading`; the rows without one follow Markdown's, as before.

## 1.2.0 (2026-11-08)

- **What someone may do per group** is a method of `People`, `may(user, right, group)`, with `RIGHTS`
  (`read`, `comment`, `write`, `manage`) and `includes`. By default everyone who may use an app may do
  everything; a project that wants less overrides it. The board asks it.
- `history.current_request()`: the request a DataGroceries view or API call is serving.
- **A mention of someone who cannot see the text's subject is muted**, in the text and while it is
  written, when the app says who can (`visible_to`, in `render`'s context and `people_json`).
  `render_markdown` takes that context as its argument.

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
