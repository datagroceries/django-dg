# Contributing to Gilde

Thank you for wanting to help. Gilde is small and opinionated, so a short look at how it is built saves
you work: read what gets in, below, before you write a large change, and open an issue to talk it over.

## Setting up

With Python 3.11 or newer:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python example/manage.py migrate
.venv/bin/python example/manage.py seed
.venv/bin/python example/manage.py runserver
```

`example/` is a Django project to try the apps in, on SQLite, with the versions of Django and the other
libraries it runs on pinned in `example/requirements.txt`; the packages themselves only set lower bounds.
`seed` makes a board with a few tickets and the user `demo` with password `demo`, to sign in as at
http://localhost:8000/admin/. The example follows your browser's language, English or Dutch.

```bash
.venv/bin/pytest -q                                  # every test
.venv/bin/ruff check --fix <files> && .venv/bin/ruff format <files>
```

GitHub Actions runs both on every push and pull request, on every supported Django and Python version and
on PostgreSQL. A pull request passes them before it is merged.

## The layout

One repository, a package per app, each released to PyPI on its own:

- `packages/django-gilde-core/`: what the apps share: the one MCP endpoint, people, notifications, the
  checks on every way in.
- `packages/django-gilde-connect/`: connecting agents: OAuth for the Claude connector, personal tokens.
- `packages/django-gilde-board/`: the kanban ticket tracker. How it is built: [docs/board.md](docs/board.md).
- `example/`: the Django project to develop in. `deploy/web1/`: Gilde's own instance.
- `docs/`: the [integration guide](docs/integrating.md), the [decisions](docs/decisions.md) and why they
  were made, and [how to release](docs/releasing.md).

## What gets in

- **Each app installs on its own.** Apps depend on core, never on each other; they work together through
  registries in core (a ticket key in a CMS page links to the board only when the board is installed).
- **Core grows only when a second app needs something**, except checking every way in and the one MCP
  endpoint, which are the point of the project. What issues tokens is in connect.
- **Agents are first-class users.** What a page can do, an MCP tool can do too, through the same code
  (an app's `operations.py`), so both follow the same rules and notify the same people.
- **Django first.** What Django has, Gilde uses, before a library or code of its own: users, groups and
  permissions, the admin, forms, messages, translation, system checks, `django.tasks`.
- **Opinionated, not configurable.** Each thing works one way, the right one, for everyone. Settings exist
  only to fit an app into its project (who the people are, its own ways in, where notifications go), never
  to have a feature another way.
- **Be sparing with features.** A new one answers a need many share, is built the way the app already
  works, and is agreed in an issue before it is built. Each app has principles of its own on top: the
  board's are in [docs/board.md](docs/board.md).

## Conventions

- English everywhere: code, comments, docs and commit messages. Texts people see are marked for
  translation, and the Dutch translation is updated with them (`makemessages`, `compilemessages`). Run
  them from an app's folder as `python -P -m django …`, so that core's own `markdown.py` does not hide
  the library of that name.
- A line in the `CHANGELOG.md` of each package a change touches, under "Unreleased".
- A decision that shapes Gilde is a dated entry in [docs/decisions.md](docs/decisions.md). One that no
  longer holds keeps its text, with a note saying what replaced it.
- Agents working in the repository read [CLAUDE.md](CLAUDE.md).

## Proposing work, asking questions

Bugs and wishes go in [GitHub issues](https://github.com/gildehq/gilde/issues), questions in
[GitHub Discussions](https://github.com/gildehq/gilde/discussions). A security problem does not: see
[SECURITY.md](SECURITY.md).

Contributions are under the [MIT licence](LICENSE), as Gilde is.
