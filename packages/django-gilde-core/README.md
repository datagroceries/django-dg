# django-gilde-core

What the [Gilde](https://github.com/gildehq/gilde) apps share. You do not install it on its own: every Gilde
app, such as [django-gilde-board](https://pypi.org/project/django-gilde-board/), brings it along.

- **One MCP endpoint for every installed app** (`gilde/mcp`). Each app registers its tools; an agent
  connects once and gets them all. A tool runs the app's own REST view, so the API and the tools follow
  the same rules. Stateless, over plain HTTP, so it runs on any WSGI server.
- **The checks on every way in.** Core issues no tokens: it lets in whatever the project and the Gilde
  packages register (personal tokens and the Claude connector's OAuth from
  [django-gilde-connect](https://pypi.org/project/django-gilde-connect/), or the project's own DRF
  authentication), and on every request checks that the person may still use the app and that the
  token covers it. A request without credentials gets a `401` that tells MCP clients where to sign in.
- **People.** Who may use an app is a Django permission; how Gilde names people, their @-handles,
  their email address and their image come from one class a project may subclass. No assumptions about
  the user model.
- **Notifications** by email, Slack, or Slack with email as fallback, once the change is committed.
- **A layout of its own**, with Bootstrap and Bootstrap Icons in the package, so the apps' pages work in
  any project; override one template to show them in yours.
- **Markdown**, rendered and sanitised the same way in every app (GitHub's lists, tables, task lists),
  with the Markdown editor, and **references between apps**: an app registers what it recognises in text,
  such as the board's ticket keys, and every app's Markdown links it while that app is installed.
- **One URL include** for every app, and **system checks** that say what a project still has to add.

Django 5.2 LTS and 6.x, Python 3.11 and newer. How to install the apps, and every setting, is in
[docs/integrating.md](https://github.com/gildehq/gilde/blob/main/docs/integrating.md).

MIT licensed.
