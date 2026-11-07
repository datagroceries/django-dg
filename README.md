<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/dg-mark-dark.svg">
    <img src="brand/dg-mark.svg" alt="" width="88">
  </picture>
</p>

# DataGroceries

Open-source Django apps that people and AI agents work on together. Each app installs on its own into a
Django project you already have, with its own login and its own users, and agents reach all of them
through one MCP endpoint.

The apps are **the board**, a kanban ticket tracker, and **the wiki**, the team's own knowledge next to
it.

## What the board does

- **A kanban board** with drag and drop, groups per team or project, each with its own columns, and
  filters on assignee, creator, label and text.
- **Tickets** with a Markdown description, labels, a size, comments with replies, and screenshots
  dropped or pasted onto the page. Parents and subtasks, blockers, duplicates and related tickets.
- **History**: every change to a ticket is kept, with who made it, and through which agent if one did.
  Each ticket shows it as one feed, with the comments and relations.
- **@-mentions and watchers**: people hear about what concerns them, by email or in Slack. With both,
  Slack comes first, and whoever is not in Slack gets an email.
- **GitHub**: a ticket links to the commits, branches and pull requests that mention its key.
- **In your project's language**: English and Dutch to start, the Django way, so another language is one
  more translation file.
- **A REST API and MCP tools** for working on tickets as on the pages: everything but deleting, uploading
  attachments, and making groups and columns.

## What the wiki does

- **Pages in one tree**: a page with pages under it is what elsewhere is a space or a folder. Addresses
  follow the tree, and a page renamed or moved keeps its old address leading to it.
- **Links between pages**, `[[Engineering/Deploying]]`, also from a ticket's text, that follow a page when
  it moves. A page lists the pages that link to it, and a ticket the pages that name it.
- **History**: every version kept, with who made it and through which agent; two versions side by side,
  and an old one brought back.
- **Comments, @-mentions and watchers**, images and files, search, translations, and pages downloaded as
  Markdown.
- **A REST API and MCP tools** for everything the pages do but uploading and downloading files.

## Why DataGroceries

- **It fits into your Django project.** A few lines in your settings and one URL include. Your login,
  your user model and your database stay as they are. `manage.py check` tells you what is still
  missing.
- **Agents work as the people who connect them.** An agent reaches only what its person may use, and
  every change it makes says so in the history. No accounts for agents, no shared keys.
- **Connecting an agent is easy.** Any MCP client connects with a personal token. Claude (claude.ai,
  Claude Desktop, Claude Code) and VS Code need only the endpoint's address and a sign-in with your own
  login.
  Projects with API logins of their own (DRF tokens, JWT, an OAuth server) can let those in instead.
- **Yours.** MIT licensed, no service to sign up for, and the data stays in your own database. The
  pages bring their own layout and assets, so they work behind a firewall and load nothing from
  elsewhere.

DataGroceries is for teams that build on Django, want their tracker and their wiki inside their own project, and
work with AI agents.

## Design principles

- **Django first.** What Django has, DataGroceries uses, rather than a library or code of its own: its users
  and your user model, groups and permissions for who may use what, the admin, the ORM and migrations on
  any database Django supports, its email settings, its task framework for sending notifications (so
  you choose the worker, and no Celery or Redis is needed), its translation machinery for the pages'
  languages, forms, messages and system checks. Whoever
  knows Django already knows how to run DataGroceries.
- **Opinionated.** Each thing works one way, chosen once and the same for everyone, so there is less to
  learn, configure and keep working. Settings exist only to fit DataGroceries into your project, such as who
  your people are or where notifications go, never to have a feature another way.
- **Agents are first-class users.** What a page can do, an MCP tool can do too, through the same code
  and under the same rules. A tool runs the app's own REST view, so the pages, the API and the agents
  can never drift apart.
- **Each app installs on its own.** Apps depend on core only, never on each other, and work together
  through core when both are installed.

## Packages

| Package | |
|---|---|
| [`django-dg-board`](packages/django-dg-board/) | The kanban ticket tracker. |
| [`django-dg-connect`](packages/django-dg-connect/) | Connecting agents: personal tokens, OAuth so Claude connects with the endpoint's address alone, and a "Connect an agent" page. Not needed if your project's own API logins are enough for your agents. |
| [`django-dg-wiki`](packages/django-dg-wiki/) | The wiki: pages in Markdown, in one tree. |
| [`django-dg-core`](packages/django-dg-core/) | What the apps share: the one MCP endpoint, people, notifications, and the checks on every way in. Comes with every app. |

Django 5.2 LTS and 6.x, Python 3.11 and newer, any database Django supports.

## Getting started

```bash
pip install django-dg-board django-dg-connect
```

```python
INSTALLED_APPS = [
    ...,
    'django.contrib.humanize',
    'rest_framework',
    'simple_history',
    'oauth2_provider',
    'datagroceries.core',
    'datagroceries.connect',
    'datagroceries.board',
]
```

```python
urlpatterns = [..., path('dg/', include('datagroceries.urls'))]
```

Then `manage.py migrate`, give a group the permission "Can use the board", and open `/dg/board/`.
[docs/integrating.md](docs/integrating.md) is the full guide: your own users, your own layout, your own API
logins, notifications, and moving your tickets over from another tracker.

## Status

Young, and used for its own development: DataGroceries' own tickets are on a DataGroceries board, which people and
agents work on together. What was decided and why is in [docs/decisions.md](docs/decisions.md). More apps
may follow, such as a CMS and a helpdesk.

## Contact and contributing

Questions are welcome in [GitHub Discussions](https://github.com/datagroceries/django-dg/discussions), bugs and
wishes in [GitHub issues](https://github.com/datagroceries/django-dg/issues). A security problem goes privately
through GitHub, as [SECURITY.md](SECURITY.md) says. To work on DataGroceries itself, start with
[CONTRIBUTING.md](CONTRIBUTING.md).

## Thanks to Eddy Grid

The board started as Eddy Board, the ticket tracker [Eddy Grid](https://eddygrid.com) built for its own team.
Eddy Grid kindly agreed to its release as open source, so it can be yours too.

## Licence

MIT, see [LICENSE](LICENSE).
