# Decisions

What was decided, when, and why, newest at the bottom. An entry that no longer holds keeps its text,
with a note that says what replaced it.

## 2026-11-05: Starting Gilde

- **Name.** Gilde, Dutch for guild: craftspeople and apprentices, people and agents, working together
  by shared rules. Packages are called `django-gilde-<app>`; `gilde` and `django-gilde` were free on
  PyPI.
- **One repository**, with a package per app. "Installs on its own" is about PyPI packages, not
  repositories; one repository keeps changes across core and an app, CI and the example project in one
  place.
- **Packages under `packages/`**, so the repository's top level keeps what is about the whole
  repository (the example project, the notes, the tooling) apart from what installs, however many apps
  there come to be.
- **On GitHub at `jaspercram/gilde`**, the simplest start. It can move to an organisation later, such
  as `django-gilde` (free when this was decided), and GitHub redirects the old links.
  *Since 6 November: the organisation `gildehq`, with gildehq.com (below).*
- **Shared code** lives in `django-gilde-core`: agent tokens with scopes, one MCP endpoint per site to
  which each installed app adds its tools (one connector on claude.ai for all of them), people (name,
  avatar, @-handle), notifications, Markdown rendering and sanitising, and references between apps.
  *Since 6 November the tokens are in `django-gilde-connect`, and Markdown is in the board until a
  second app needs it.*
- **Work locally first**, in Claude Code on this computer, with Eddy Grid beside it to copy from. Cloud
  sessions come later, for well-described tickets.
- **No server yet.** The Hetzner server can later host a public demo with a live MCP endpoint.
  *Since 6 November Gilde's own instance runs on it (`deploy/web1/`).*

## 2026-11-05: The board starts from Eddy Board

The board is a copy of Eddy Board, the ticket tracker Eddy Grid built for its own use, with its REST
API and MCP tools. It is a copy, not a shared codebase: Eddy Grid keeps its own code, and there is no
migration of its data. Eddy Grid may switch to this board later, but nothing here plans for it.

Left out of the copy: a few later changes, which can be made here again where they fit, and the import
from Jira with its legacy keys.

What tied Eddy Board to Eddy Grid, and what replaces it:

| In Eddy Grid | In Gilde |
|---|---|
| Avatars from its own user details, and staff as who takes part | A people provider in core: name, avatar, @-handle and who takes part; initials by default |
| Its own base template | Kept at first: the host project's `base.html` (since replaced by Gilde's own layout) |
| Slack through its own helpers, on a task queue | Notification backends in core, sent once the change is committed |
| Its own file storage | Django's storage API |
| The REST API and MCP tools in its own API, with its own tokens | Tokens and the MCP endpoint in core; the board registers its own tools |
| A card on its own dashboard | Stays in Eddy Grid |
| GitHub links, colours, key prefix | Already settings; carried over |

## 2026-11-05: The agent foundation in core

*Since 6 November: the personal tokens are in `django-gilde-connect`, at `gilde/connect/`, with OAuth for
the Claude connector beside them; an area is for whoever has its permission; and the pages bring their
own layout. See "Core checks credentials, connect issues them" and "Fitting into any Django project".*

- **Areas.** Each app registers an area with gilde.core (`areas.py`): a token scope, who may use it,
  a sentence for the agent, and its MCP tools. The board's is `board`, for the members.
- **Personal tokens** (`ApiToken`), made and revoked on `gilde/tokens/`, as in Eddy Grid: hashed, scoped
  to areas, until revoked by default, stopped by three months without use or by losing access.
- **One MCP endpoint**, `gilde/mcp`, written ourselves as Eddy Grid's is: stateless JSON-RPC over plain
  HTTP, each tool a REST view run in-process. It lists the tools of every area the token opens.
- **No OAuth yet.** Claude Code and other clients send the token as a header; claude.ai's connectors
  need OAuth, which comes when someone needs it there.
- **Notifications** run on Django's own task framework (`django.tasks`) instead of Celery, so a project
  needs no worker to start; one with a worker sets up a task backend. A message is a summary, a link
  and a quote, which the email and Slack channels each lay out.
- **The host's `base.html`** gives the pages Bootstrap 5, Bootstrap Icons and messages; the board brings
  its own scripts, htmx included.

## 2026-11-05: MIT

- **The MIT licence**, for the repository and every package, so any Django project can take an app in
  without legal questions. Eddy Grid agreed to Eddy Board's code being released as open source.

## 2026-11-05: MCP and a REST API

- **Both, as one.** Each app's REST API is public, and its MCP tools are that same API run in-process:
  the same views, rules, token and answers. An agent connects through MCP; a script, CI job or webhook
  that speaks no MCP uses plain HTTP.
- **MCP first in the docs.** The READMEs lead with the MCP endpoint, and describe the REST API as the
  same tools over HTTP.
- **Stable from version 1.** Before it, both may change without notice; from it, a change that breaks
  a client needs a new major version.
- **Gilde's own tokens, and the host's.** A Gilde token is scoped to areas and works in any project.
  A project that has API tokens or OAuth of its own lists their DRF authentication classes in
  `GILDE_AUTHENTICATION_CLASSES`, so its people need no second token; a request let in that way reaches
  every area its user may use. A Gilde token still opens nothing of the host's.

## 2026-11-05: The host project says who takes part

*Since 6 November, who takes part is a Django permission per app, and `GILDE_PEOPLE` replaces the three
settings below ("Django first", and "Fitting into any Django project"). Handles stay as decided.*

- **Who takes part is the host's choice**, not staff alone: `GILDE_MEMBERS` names a function that
  returns them. They reach the apps and their areas, and can be assigned and @-mentioned. Without it,
  the active staff users, as an internal tool is the safe default.
- **Handles don't come from email addresses.** People in one project may have addresses at different
  domains, or none. A handle is the username by default (unique by definition), or what the function
  in `GILDE_HANDLE` returns.

## 2026-11-06: Django first

- **What Django has, Gilde uses**, before a library or code of its own: users, groups and permissions,
  the admin, forms, messages, translation, system checks, `django.tasks`. The integrator manages Gilde
  with what they know already, and Gilde behaves the way the rest of their project does.
- **Rights are Django permissions.** Who may use an app is one ("Fitting into any Django project"). When an app later lets
  some people do more than others, such as who may change a board's columns, each such right is
  another permission of that app, granted to groups in the admin. The page and the MCP tool check the
  same permission, so an agent never does more than its person may. Gilde has no roles of its own.

## 2026-11-06: The second app is the CMS, and Gilde's website runs on it

*No longer holds: the wiki came second, and the CMS waits (2026-11-07, below).*

- **The CMS comes second**, before the wiki and the other ideas: Gilde's own website runs on it from the
  start, which shows the CMS working and is the second app that tests whether apps install on their own
  and work together through core. The wiki is for a team's own knowledge, edited live; a public site
  wants drafts that are published when ready, pages and posts, which is a CMS.
- **1.0 does not wait for it.** The packages go out with the README on GitHub and PyPI as their only page;
  the website, and the big announcement that links to it, follow once the CMS runs.
- Tracked on Gilde's own board: G-18 (the CMS) blocks G-9 (the website), which blocks G-10 (the
  announcement).

## 2026-11-06: Core checks credentials, connect issues them

How a program gets in, so that a project with its own logins, users and tokens needs nothing twice, and
Claude still connects with one URL. Worked out in a design proposal, tried in a spike, then built.

- **Core is a resource server only.** It checks every way in the same way and issues no tokens: the
  person may still use the app, and the token's scope, when it has one, covers it. Ways in are Gilde
  packages that register (`gilde.core.authentication.register`) and the project's own DRF authentication
  classes (`GILDE_AUTHENTICATION_CLASSES`). A request without credentials gets a `401` pointing at the
  protected resource metadata (RFC 9728), which names the authorization server: a registered one, or
  the project's own (`GILDE_AUTHORIZATION_SERVER`).
- **`django-gilde-connect` issues them, and is optional.** OAuth for the Claude connector on
  django-oauth-toolkit 3.4, as Eddy Grid's runs in production: PKCE only, Client ID Metadata Documents
  from an allowlist of Claude's hosts, no dynamic client registration until a client needs it, rotated
  refresh tokens, only hashes stored and no grace period (the two cannot go together). The personal
  tokens moved here from core. One page, "Connect an agent", lists every connection and token.
- **Not allauth's provider**, which would force allauth's login on projects that have their own; not an
  OAuth server of our own, the most security-sensitive part.
- **Personal keys start with `gilde_`**, so a leaked one is recognised and a project's own Bearer tokens
  are told apart.
- **Everything under one prefix.** claude.ai found the discovery documents under `/gilde/` (tried on web1),
  so a project needs no URL at its site root.

## 2026-11-06: Fitting into any Django project

- **Who may use an app is a Django permission** of that app's ("Can use the board"), granted to groups
  in the admin; superusers have it. Its holders are the app's people: they can be assigned and
  @-mentioned.
- **One class for how Gilde sees people**, `gilde.core.people.People`, named in `GILDE_PEOPLE`, as allauth's
  adapters: who may use an app, names, handles, email addresses, images. Its defaults assume nothing about
  the user model beyond Django's `AbstractBaseUser`.
- **The pages bring their own layout** (`gilde_core/base.html`) and their own assets, so they work whatever
  the project's front end and load nothing from elsewhere. A project that wants them in its own layout
  overrides that template, as with the admin; no setting.
- **One URL include**, `path('gilde/', include('gilde.urls'))`, for every installed app and the MCP endpoint.
- **No required settings**, and **system checks** that say what is still missing.
- **Django 5.2 LTS and 6.x, Python 3.11 and newer**, as most projects that would install Gilde run 5.2.
  Notifications use `django.tasks`, its backport, or else go out in the request.
- **The API names people by handle**, with their email address beside it when they have one.
- **The pages are translated** the Django way; English and Dutch to start. The API and the MCP tools stay
  English, for agents.

## 2026-11-06: GitHub organisation and domain

- **gildehq.com** and the GitHub organisation **`gildehq`**, matching, without "Django" in the name; the
  packages keep `django-gilde-*` on PyPI, where people look for Django apps. The public repository will be
  `gildehq/gilde`, starting from a new history; the private one keeps the old.
- **Moved before going public**: `gildehq/gilde` was made on 6 November, private, from one commit with
  the files as they were; the old history is kept privately as `jaspercram/gilde-archive`. Going public
  (once Eddy Grid confirms) is then a switch in the settings, and the board's link to GitHub and web1's
  checkout point at the repository for good.

## 2026-11-06: The logo

- **A guild hall**: a roof on three pillars and a base, for a guild's house and the apps under one roof.
  Chosen over a shield, two overlapping circles and a monogram, as it says the name and stays clear at 16
  pixels.
- **Indigo (`#3730a3`) with one amber pillar (`#f59e0b`)**: the amber pillar is the app at hand, so each app
  may later colour its own. On dark backgrounds, `#c7d2fe` and `#fbbf24`.
- The files are in `brand/`: the mark for light and dark backgrounds, the avatar for GitHub and PyPI
  (with a 500 px PNG), and the favicons, which Gilde's own layout uses.

## 2026-11-07: The wiki comes second; the CMS waits

- **The wiki is the second app** (G-17), for a team's own knowledge next to its board. The CMS (G-18) went
  to the Icebox on 6 November: with its content model and its look both in code, our own would largely
  rebuild Wagtail, so when it is picked up the first question is whether Wagtail with a Gilde layer for
  agents is the better route. Its design is on G-18.
- **One tree of pages, addresses that follow it.** No spaces or books beside the pages: a page with pages
  under it is one. An address is a page's place, and an old one keeps leading to its page.
- **Links between pages are written as people name pages**, `[[Engineering/Deploying]]`, absolute or
  relative as with folders, and are rewritten when a page moves, so a link stays readable and right. They
  are a reference in core's Markdown, so a ticket can link to a page too.
- **What a second app needed moved to core**: attachments, @-mentions, the writing help, the notification
  helpers, what the REST APIs share, and `backlinks`, the registry through which a ticket lists the wiki
  pages that name it. Each app keeps its own tables for comments, watchers and files.
- How it is built: [wiki.md](wiki.md).
