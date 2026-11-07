# Fitting Gilde into your Django project

How to add the Gilde apps to a Django project you already have, whatever it uses for logins, users,
API tokens and its front end. It describes what works today; the board is the only app so far.

Status: tested once, on 6 November 2026, in a fresh [cookiecutter-django](https://cookiecutter-django.readthedocs.io/)
project: Django 6.0, Python 3.14, allauth with sign-in by email, a user model with a single `name` field,
and DRF with its own tokens. Following this guide, it took six lines in `INSTALLED_APPS`, one URL, and
one setting to let its DRF tokens in; the pages, the API, the MCP endpoint, the "Connect an agent" page
and the OAuth sign-in all worked. Gilde's own instance runs on PostgreSQL, and CI runs every test on
PostgreSQL too. Until 1.0, anything may change.

## In short: what you write

**What you must write** is a few lines, and nothing else:

- the packages in `INSTALLED_APPS`;
- one URL include;
- `manage.py migrate`;
- in the admin, a group that may use each app.

**What you may write**, only to fit Gilde to your project:

- settings, each with a default (below);
- one class that says how Gilde sees your users (`People`);
- your own version of one template, to show Gilde's pages inside your own layout;
- the classes of your own API logins, or the address of your own OAuth server, so your people need no
  second token.

**What you should never need to write**, and should tell us about if you do:

- middleware;
- subclasses or copies of Gilde's views, forms, models or other templates;
- code that writes to Gilde's tables yourself (use the API or MCP endpoint instead);
- a token system for agents.

`manage.py check` tells you what is still missing, and how to fix it.

## What you need

- Python 3.11 or newer.
- Django 5.2 LTS or 6.x.
- Any database Django supports.
- Any user model: Gilde makes no assumptions about its fields (see "Your users").

## Installing

```bash
pip install django-gilde-board django-gilde-wiki django-gilde-connect
```

Take the apps you want: the board, the wiki or both. That brings `django-gilde-core`, Django REST framework, django-simple-history and django-oauth-toolkit
with it. `django-gilde-connect` lets Claude and other agents connect; leave it out if your project has
its own API logins and you need no Claude apps (see "Agents and the API").

```python
INSTALLED_APPS = [
    ...,
    'django.contrib.humanize',
    'rest_framework',
    'simple_history',
    'oauth2_provider',  # for gilde.connect
    'gilde.core',
    'gilde.connect',
    'gilde.board',
    'gilde.wiki',
]
```

```python
urlpatterns = [
    ...,
    path('gilde/', include('gilde.urls')),
]
```

The include mounts every installed Gilde app and the shared endpoints under the prefix you choose:

- the board at `gilde/board/`, the wiki at `gilde/wiki/`;
- the MCP endpoint at `gilde/mcp`;
- with connect, the "Connect an agent" page and the OAuth endpoints at `gilde/connect/`.

Then:

```bash
python manage.py migrate
python manage.py check
```

Gilde also needs these from Django's usual setup, and `check` tells you if one is missing:

- the template context processors `request`, `auth` and `messages`;
- a `LOGIN_URL` that leads to your sign-in page.

## Who may use what

Who may use an app is a Django permission of that app's. For the board it is "Can use the board",
`gilde_board.use`; for the wiki "Can use the wiki", `gilde_wiki.use`. You grant it like any other permission:

1. In the admin, make a group, say "Team".
2. Give that group the permission "Can use the board", and "Can use the wiki".
3. Put people in the group.

Superusers have every permission. Until a group or a person gets it, nobody else may use the app, and
`manage.py check` warns about that.

The people who may use an app are its people: they can be assigned and @-mentioned there. Losing
the permission ends their access at once, on the pages and for every token or connected agent.

## Your users

Gilde sees your users through one class, `gilde.core.people.People`. Its defaults:

| Method | Default |
|---|---|
| `may_use(user, area)` | an active user with the area's permission |
| `members(area)` | everyone who may use the area, sorted by name |
| `name(user)` | first and last name, or a `name` field, or else the username |
| `short_name(user)` | the first name, or the first word of the name |
| `handle(user)` | what follows the @ in a mention: the username, lowercased, with "-" for characters a handle cannot hold (`anna@example.com` becomes `anna-example.com`) |
| `email(user)` | the field your model names as its email field, or None |
| `avatar_url(user, size)` | None, so people show as their initials |
| `language(user)` | a `language` field on your user model, if it has one; else None, so notifications are in `LANGUAGE_CODE` |

These defaults use only what Django's own `AbstractBaseUser` promises. A user model with a single `name`
field and email sign-in, as cookiecutter-django makes, works without code. People without an email
address work too; they just get no notifications.

To change what differs, subclass it and name the subclass in your settings:

```python
# yourproject/gilde.py
from gilde.core.people import People


class OurPeople(People):
    def avatar_url(self, user, size):
        photo = user.profile.photo
        return photo.url if photo else None

    def handle(self, user):
        return user.profile.nickname or super().handle(user)
```

```python
GILDE_PEOPLE = 'yourproject.gilde.OurPeople'
```

To decide who may use an app by a rule of your own instead of the permission, override `may_use`. Also
override `members` with a query, because otherwise Gilde has to ask `may_use` about every user:

```python
class OurPeople(People):
    def may_use(self, user, area):
        return user.is_active and user.profile.is_employee

    def members(self, area):
        users = get_user_model().objects.filter(is_active=True, profile__is_employee=True)
        return users.order_by('name')
```

A handle may hold letters, digits, ".", "_" and "-", and no two people may share one. A handle that
breaks those rules reaches nobody.

Where people sign in with their email address, as in cookiecutter-django, the username is that address,
so the default handle is `ann-acme.com` for `ann@acme.com`: unique, but long. If everyone who uses Gilde
has an address at your own domain, the part before the @ is a shorter handle:

```python
class OurPeople(People):
    def handle(self, user):
        local, _, domain = user.email.partition('@')
        return local if domain == 'acme.com' else super().handle(user)
```

Choose handles once: an @-mention is stored as written, so after a change of handle the older ones no
longer reach the person.

## How the pages look

The pages speak your project's language, the Django way: `LANGUAGE_CODE`, or the visitor's own with
Django's `LocaleMiddleware`, which takes the browser's language and remembers a choice. With the
middleware, Gilde's own layout has a language switch in its top bar, offering the languages of your
`LANGUAGES` that Gilde speaks too; set `LANGUAGES`, or it offers every one Gilde has. Gilde ships English
and Dutch; another language is one more `.po` file per package. The REST API and the MCP tools stay
English whatever the language, as they are for programs and agents. A notification is in the language
of the person it goes to, whatever language the change was made in: Django keeps no language per person,
so it is what your `People` class's `language(user)` says (below), and `LANGUAGE_CODE` when it says
nothing.

Gilde's pages bring their own layout, `gilde_core/base.html`: Bootstrap 5 and Bootstrap Icons, a thin
bar with a link back to your site, and Django's messages. They work whatever your front end is, and all
their CSS, JavaScript and fonts ship in the packages. No page loads anything from another site, except
the avatars your `People` class may point at, so they work offline, on an internal network and under a
strict Content Security Policy.

To show them inside your own layout instead, override that one template, as you would the admin's.
Put a `gilde_core/base.html` in your project's templates, in a directory listed in `TEMPLATES['DIRS']`,
which Django searches before the apps' own. It must:

- load Bootstrap 5.3 and Bootstrap Icons 1.13. The bundled copies are at
  `{% static 'gilde_core/vendor/bootstrap/bootstrap.min.css' %}`,
  `{% static 'gilde_core/vendor/bootstrap/bootstrap.bundle.min.js' %}` and
  `{% static 'gilde_core/vendor/bootstrap-icons/bootstrap-icons.min.css' %}`;
- show Django's messages;
- have the blocks `title`, `extra_head`, `content`, `container_class` and `extra_scripts`.

Leave every other Gilde template alone; they change between versions.

## Agents and the API

Every app has a REST API and tools on the one MCP endpoint, and both act as the person who connected
them, under the same rules as the pages: the board's API at `gilde/board/api/tickets/`, the wiki's at
`gilde/wiki/-/api/pages/`, and their tools, such as `search_tickets` and `get_page`, at `gilde/mcp`. How
a program gets in depends on what your project has.

**The Claude connector, with `django-gilde-connect`.** Everyone finds a "Connect an agent" page at
`gilde/connect/`, linked from each app, which says how:

- **Claude** (claude.ai, Desktop, mobile): add a custom connector with the address of the MCP endpoint,
  `https://<your site>/gilde/mcp`. Claude sends the person here to sign in, through your own login,
  whatever it is, and to allow it.
- **Claude Code**: `claude mcp add --transport http gilde https://<your site>/gilde/mcp`, then `/mcp` to
  sign in in the browser.
- **VS Code** (Copilot in agent mode): the endpoint as an `http` server in `.vscode/mcp.json`; starting it
  signs in in the browser the same way.
- **Anything else** (Cursor, scripts, CI, agents without OAuth): a personal token, made on the same page,
  named and limited to the apps ticked, sent as `Authorization: Bearer gilde_…`. Signing in is open only
  to these well-known clients: any other could register by its own address and ask people to let a
  lookalike act as them.

The page lists every connected app and token, each revocable. A connection or a token stops when it is
revoked, after three months unused, or when its person may no longer use the app. The Claude apps reach
your site from Anthropic's servers, so only over HTTPS on the internet; Claude Code connects from the
person's own computer, so it works on an internal network too.

Connect runs django-oauth-toolkit as an OAuth server, set up as the Claude clients need it. If your
project sets `OAUTH2_PROVIDER` itself, what you set is kept and connect fills in the rest.

**Your own API logins** (DRF tokens, JWT, anything a DRF authentication class checks). List the classes,
and your people use what they already have:

```python
GILDE_AUTHENTICATION_CLASSES = ['rest_framework_simplejwt.authentication.JWTAuthentication']
```

With connect installed as well, Gilde's own keys start with `gilde_`, so a token of yours is never
mistaken for one. Without connect, your own logins are the only way in.

**Your own OAuth server** (Keycloak, Auth0, Entra, allauth's provider). Name it, and the MCP endpoint's
`401` sends MCP clients there to sign in (the protected resource metadata of RFC 9728, at
`gilde/.well-known/oauth-protected-resource`):

```python
GILDE_AUTHORIZATION_SERVER = 'https://login.example.com'
GILDE_AUTHENTICATION_CLASSES = ['yourproject.auth.OAuthTokenAuthentication']
```

The authentication class checks your server's tokens. When a token carries a `scope`, Gilde reads it as
the app names it may open, such as `board`. Leave connect out in this case: your server signs people in.

Changes made through the API say so in the history: "via Claude Code on my laptop", or "via API" for a
token of your own.

## Notifications

People hear about what concerns them: being assigned, @-mentioned, or a change on a ticket they watch.

| Setting | Default | |
|---|---|---|
| `GILDE_NOTIFICATIONS` | `['email']` | the channels to try, in order, for each person: `'email'` sends through your email settings; `'slack'` sends a direct message to the Slack user with the same email address |
| `GILDE_SLACK_BOT_TOKEN` | – | the token of a Slack bot with the scopes `users:read.email` and `chat:write`, for `'slack'` |

With `['slack', 'email']`, people get a Slack message, and an email when Slack cannot reach them: they
are not in the workspace, or Slack is down. Someone no channel reaches is logged as an error, and the
others still hear about it. `manage.py check` refuses an unknown channel, and Slack without a token.

A message goes out as a task once the change is committed:

- On Django 6 it is a task on your `TASKS` backend. Django's default backend sends it at once, inside
  the request; configure a backend with a worker to send it in the background.
- On Django 5.2 the `django-tasks` backport is used if it is installed, and otherwise the message goes
  out inside the request.

## The board's settings

| Setting | Default | |
|---|---|---|
| `GILDE_BOARD_NAME` | `'Board'` | what the board is called on its pages |
| `GILDE_BOARD_KEY_PREFIX` | `'T'` | the start of every ticket's key, as in T-123 |
| `GILDE_BOARD_DISPLAY_TIMEZONE` | `TIME_ZONE` | the timezone the pages show times in |
| `GILDE_BOARD_COLORS` | see `conf.py` | the colours of the column categories, of blocked tickets, and the accents that tell labels and people apart |
| `GILDE_BOARD_GITHUB_REPOSITORY`, `_TOKEN`, `_WEBHOOK_SECRET` | empty | link code in a GitHub repository to the tickets it mentions: see the [board's README](../packages/django-gilde-board/README.md#github) |

## The wiki's settings

| Setting | Default | |
|---|---|---|
| `GILDE_WIKI_NAME` | `'Wiki'` | what the wiki is called on its pages |

The wiki's pages offer the languages of your project's `LANGUAGES` for a page and its translations.

## What `manage.py check` tells you

| ID | What | What to do |
|---|---|---|
| `gilde.E001` | an app Gilde needs is not installed | add it to `INSTALLED_APPS` |
| `gilde.E002` | a context processor is missing | add it to `TEMPLATES` |
| `gilde.W001` | Gilde is not in the URLs | add `path('gilde/', include('gilde.urls'))` |
| `gilde.W002` | `LOGIN_URL` leads nowhere | point it at your sign-in page |
| `gilde.W003` | only superusers may use an app | grant its permission to a group |
| `gilde_board.E001` | `django.contrib.humanize` is not installed | add it to `INSTALLED_APPS` |
| `gilde.E003` | `GILDE_NOTIFICATIONS` lists an unknown channel | list `'email'` and `'slack'` only |
| `gilde.E004` | Slack without `GILDE_SLACK_BOT_TOKEN` | set the bot's token |
| `gilde_connect.E001` | django-oauth-toolkit is not installed | add `'oauth2_provider'` to `INSTALLED_APPS` |

## Moving your tickets over

To bring the tickets from another tracker (Jira, Trello, GitHub Issues, a spreadsheet), we recommend
letting an agent do it. Connect Claude Code, or Claude with access to the other tracker, and ask it to
copy the tickets over. It reads the old tracker however that allows (its API, an export) and writes
through the board's MCP tools, the same rules as the pages: it can make tickets with their
description, group, column, assignee, labels and parent, add comments, relate and block tickets.

Before you start:

- **Make the groups and columns on the board first**, in the pages: the API and the tools do not make
  them. Tell the agent which old status goes to which column.
- **Everything is done as the person who connected the agent**, today. The board's history shows that
  person as the creator of every ticket and the writer of every comment, "via Claude". Ask the agent to
  start each description and comment with who wrote it and when, such as "Originally by Ann Smith, 3 March
  2025", so that stays known.
- **People hear about it.** Assigning someone and @-mentioning them in a description or comment notifies
  them, as on the pages. Have the agent leave the assignees out until the end, or write names without
  the @, or tell your team a move is coming.
- **Attachments are not in the API.** Ask the agent to link to them in the old tracker instead, while it
  still runs.
- **Try a handful first**, check them on the board, then let it do the rest. Ask it to keep a list of old
  and new keys, so links between tickets and from elsewhere can be followed.

Nothing is deleted through the API, so a move that went wrong is cleaned up on the pages.
