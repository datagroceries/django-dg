# Decisions

What was decided, when, and why, newest at the bottom. An entry that no longer holds keeps its text,
with a note that says what replaced it.

## 2026-11-05: Starting Gilde

*The name no longer holds: Gilde became DataGroceries (2026-11-07, below).*

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
  *Since 7 November how a message reaches someone is a hook, `Notifier`, and Slack left core.*
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

*No longer holds: the organisation becomes `datagroceries`, the domain datagroceries.com (2026-11-07, below).*

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

## 2026-11-07: Gilde becomes DataGroceries

- **Why.** Gilde Software B.V. holds the EU trademark "GILDE by CRAFTVIEW" (018977686, registered June
  2024) for software and IT services: the same word, in the same field. Renaming before the repository goes
  public and the packages reach PyPI costs a day; after, it would cost every project that installed them.
- **DataGroceries**, the name of Jasper's company, whose domain he has held for years: nobody can say it
  imitates another, and it needs nothing new bought or registered. Hofje and Steading, checked as well,
  were free, but a name of its own would be one more thing to keep.
- **The names.** `django-dg-<app>` on PyPI, short; `datagroceries.<app>` to import, as a module name has no
  hyphen and `dg` is taken on PyPI; `dg_<app>` as app labels, so tables, permissions, templates and static
  files; `DG_*` settings; `dg-` in CSS. The GitHub organisation `datagroceries`, the repository `django-dg`.
- **Where it runs.** The own instance at hq.datagroceries.com, the demo at demo.datagroceries.com; the
  server's own names (its user, folders and services) stay `gilde` for now, as nobody sees them.
- Since nothing was released, each app starts again from one migration; the own instance's data moved to
  the new tables. The logo stays: a house with the apps under one roof.

## 2026-11-07: Hooks, not choices

*Sharpened the same day by "A good default, and room to integrate fully": the defaults may be as
complete as we like.*

- **A hook the integrator replaces entirely**, with a default that is safe and needs no code for the common
  case, wherever a project may want something its own way. The integrator programs as well as we do, so we
  fill in nothing for them, and we assume nothing about the project beyond Django itself, so the apps fit
  whatever setup is already there. In CONTRIBUTING.md, under "What gets in".
- **Who may use an app stays Django's permission** ("Can use the board"), behind `People.may_use`: one tick
  in the admin for the common case, overridable as a whole. `is_staff` was weighed and left: it means "may
  sign in to the admin", which is not who should use a wiki. "Every signed-in user" was left too: in a
  project where customers have accounts, it would open the board to them.
- **Access per board group (G-32) is a hook on `People` too**, `may(user, right, group)`, which by default
  allows everything to whoever may use the board. Not a Django authentication backend: every installation
  would have to add it to `AUTHENTICATION_BACKENDS`, and projects with backends of their own would have to
  fit it in. An integrator who wants restrictions uses `has_perm`, django-guardian or a model of their own
  inside the hook.
  *Built on 7 November, as described; the demo lets visitors work on tickets but not manage groups.*

## 2026-11-07: Notifications are a hook (G-47)

- **Why.** Notifications were a choice from a menu, `DG_NOTIFICATIONS` with `'email'` and `'slack'` in the
  order to try them: what "Hooks, not choices" rules out. A project with Teams, its own Slack ids, a digest
  or people's own preferences could not plug them in, and core needed `requests` for a Slack that none of
  our own projects uses. It came along from Eddy Grid.
- **One class, `Notifier`, named in `DG_NOTIFIER`**, as `People` in `DG_PEOPLE`. Its `send(user, message)`
  gets the user, not an address, so it can reach them any way it likes, or not at all. The default emails
  `people.email(user)` through Django's email settings, with no code needed.
- **The apps keep deciding who hears about what**, core says it in each person's language and sends it as
  a task once the change is committed, leaving out inactive users. A notifier that raises is logged, and
  the others still hear.
- **Slack left core** for a dozen lines in integrating.md, with email for whoever Slack cannot reach.
- **The notifier gets the event, not only a sentence**: `kind`, `actor`, `subject` and the ticket or page
  itself (`about`), besides the summary, link and quote. With only a sentence, a project could change
  the channel but not choose by what happened (Slack for mentions, email for the rest), group a digest
  by ticket, or build a message of its own: not "integrate fully". One call per person stays; a team
  channel per event would need a language for the channel, and waits until someone asks.
- **The default email is a good one**: from templates a project overrides, with the ticket or page as
  subject and in one thread (`In-Reply-To`/`References`), HTML beside the text, and why it came.
- **Not backwards compatible.** 1.0 was a day old, so `DG_NOTIFICATIONS` and `DG_SLACK_BOT_TOKEN` went
  without a transition; the changelog says so. Released as 1.1.0 of core, board and wiki rather than
  2.0.0, for the same reason; board and wiki 1.1.0 need core 1.1.0.

## 2026-11-07: A good default, and room to integrate fully

- **The point is not that the integrator does everything, but that they can.** Permissions, sign-in for
  agents and now notifications each raised the question how much DataGroceries should do itself. The
  answer is the same each time: a default as good as we can make it, needing no code, and a hook through
  which the project takes the whole thing over, so the apps become part of it rather than sit beside it.
- **What it is for:** nobody makes an account twice or signs in twice, and no part speaks another
  language, or shows another time, than the rest of the project.
- **It replaces "we fill in nothing for them"** in "Hooks, not choices". A choice from a menu of ours is
  still not a hook. In CONTRIBUTING.md and the README's design principles.
- **Without a project of its own**, DataGroceries runs in a small one made for it, as its own instance
  does (`deploy/web1/`). The README says so instead of "nothing to run it in".
- **The board's times follow Django's current timezone**, as the wiki's already did, so a project that
  activates each person's own timezone gets it on every page. `DG_BOARD_DISPLAY_TIMEZONE`, one zone for
  everyone, went. `People` does not say a person's timezone: no message to someone else has a time in
  it yet; when one does, it gets `timezone(user)` as `language(user)`.

## 2026-11-09: Access per page in the wiki (G-56)

- **Every page is asked about, however deep**, through the same `People.may(user, right, where)` as the
  board's groups, with `TOP` for the top. First proposed was access per top-level page only, as a "space",
  since it would be predictable and cheap. Jasper preferred all pages equal: the wiki has no spaces on
  purpose (a page with pages under it is what elsewhere is a folder), and a project that wants spaces
  looks only at the topmost page in its `may`. Asking about every page is the more general hook; per
  space is one way to answer it.
- **Reading a page needs read on every page above it**, and the wiki enforces this itself rather than
  leave it to the project: a page's address holds the slugs of the pages above it, and the crumbs and the
  tree show their titles, so a readable page under an unreadable one would give them away. It is what
  Confluence does with view restrictions. Writing and commenting are the project's alone.
- **The project names a page by the page, not its address**, in its own rules: an address changes with
  a rename or a move above it, and a rule by address would stop counting without a word.
- **`manage` goes unused in the wiki.** With all pages equal there is nothing above `write` to manage:
  starting a page at the top is `write` on `TOP`.
- **Fast enough for thousands of pages.** The answers are remembered per request, a branch someone may not
  read is skipped whole, and nothing is asked when the project leaves `may` as it is. Measured on 3,030
  pages: some 10 ms more than before per page by default, some 30 ms with rules per page.

## 2026-11-09: Wiki links are relative, as in a browser (G-61)

*Sharpened the same evening by "Pages and folders" (G-62), below: a link starts in the folder it is written
in, and not every page is a folder.*

- **A link means one address.** "The end of an address will do" made `[[infra]]` on the page Sales find
  `/engineering/infra`, and a page made elsewhere later could change where a link went. Now a link starts
  from the page it is in, as a relative address does in a browser, or from the top with `/`; nothing is
  looked for anywhere else.
- **Every page is a folder of the pages under it**, as its address ends in `/`: `[[Rollback]]` and
  `[[./Rollback]]` are under it, `[[../Onboarding]]` beside it. Two other routes were weighed. A page
  with pages under it as a folder's index and one without as a file makes `[[Platform]]` the page beside
  it, but a link changes meaning when a page gets its first page under it, which would need rewriting
  behind the writer's back. Every page as a file beside a folder of its name keeps links stable and short
  to the pages beside it, but a link to a page under it repeats the page's own name. Jasper links mostly
  to the pages under a page, and wanted nothing to happen by itself: so the first route.
- **Outside the wiki only a link from the top is one**, as a ticket has no place in the tree to start
  from. The API and MCP tools take whole addresses only.
- **Not backwards compatible**, as nobody uses the wiki yet: the seeds were rewritten; hq's test page was
  left as Jasper wrote it.

## 2026-11-09: Pages and folders (G-62)

- **A page is a page of its own or a folder**, as files and folders are, and a link starts in the folder it
  is written in. Every page a folder (G-61) made the links to the pages in a folder short, but those to a
  page's neighbours `[[../Platform]]`; Jasper links from a folder mostly to its pages, and from a page
  mostly to its neighbours, so both should be short.
- **Nothing happens by itself.** A page with pages under it becoming a folder of itself would change what
  its links mean behind the writer's back. So it becomes one only through "Make it a folder", which keeps
  its address and rewrites its own relative links to name what they named, as moving a page already does;
  a folder with nothing in it becomes a page again the same way.
- **Inside, one kind of thing**: a page with a flag, `folder`, rather than files and folders of their own,
  or an "index" page per folder. The tree, rights per page (G-56), history and dragging stay as they were.
- **A folder's address ends in "/"**, a page's does not, so that the browser agrees with the wiki on every
  relative link, and a download is a real folder, its text `home.md`.

## 2026-11-09: Versions in other languages; one name per folder (G-64)

- **"Translate" became "In another language"**: the wiki writes no translation, a person or an agent
  does. Besides a new page to translate, a page already there in another language can be linked as a
  version, and unlinked again, as Jasper first expected.
- **Only a page with a language has versions**, and a folder none: a folder is in no language of its own.
  Separate folders per language (`/nl/...`, `/en/...`) with their pages linked is the way to a tree per
  language.
- **One name per folder, everywhere**, as in a file system. Two versions of a page beside each other both
  called Platform confused, and with exact addresses `[[Platform]]` finds only one of two pages of a name;
  the second is refused rather than made `platform-2`.

## 2026-11-09: The wiki starts with its page "home" (G-65)

- **An ordinary page, not a text of its own.** The start page was first the wiki's own text, as the top
  folder's (TopText), but it lacked what every page has, comments, a language, versions; Jasper wanted it
  to be a page with exactly the same workings, or none. So the wiki starts with its page `home` at the top,
  as a site's `/` shows its `index.html`; until there is one, with what changed lately, as before.
- **"home", not "index"**: a name everyone reads in the tree, and the same for a folder's own text in a
  download (`home.md`), though tools such as MkDocs look for `index.md`.
- **No setting names it**: a setting would be a feature another way, and would stop counting when the page
  was renamed.
