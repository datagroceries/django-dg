# Changelog of django-dg-wiki

## Unreleased

Needs django-dg-core 1.3.0.

- **Access per page.** What someone may do on a page, read, comment or write, is the project's
  `People.may(user, right, page)`, asked about any page however deep, and about `TOP` for the top. By
  default everyone who may use the wiki may do everything, as before. Reading a page needs read on every
  page above it. Who may not read a page does not see it, nor the pages under it, anywhere: the tree,
  search, the API and MCP tools, downloads, files, old addresses, and the wiki pages a ticket lists. A link
  to it shows by the name the link gave it, a mention of someone who cannot see a page is muted, and they
  do not hear about it. Controls show only to whoever may use them.
- A link may end in a `/`, which changes nothing: `[[Sales/]]` is `[[Sales]]`, and a link to no page so
  written shows its name instead of nothing. A link to no page with no name to show, as `[[..]]` with no
  page above, stays text as written.
- Following a link to a page that is not there yet starts it where the link says, with the title it gives,
  no longer under a page or by a title of your choice, so the link finds it; a page above it that is not
  there either is offered to be started first.
- **Pages and folders.** A page is a page of its own or a folder, whose text is the index of the pages in
  it; only a folder has pages in it. A folder's address ends in `/`, a page's does not. "Make it a folder"
  and "Make it a page" (and `folder` in the API and MCP tools) change it, keeping its address and
  rewriting the relative links in its text. A download is as a real folder: `engineering/index.md` beside
  `engineering/platform.md`. Needs the migration `0002_page_or_folder`, which makes the pages with pages
  under them folders.
- **A link starts in the folder it is written in, as a relative address does in a browser**:
  `[[Platform]]` is the page in a folder, or beside a page, `[[../Sales]]` one folder up, and
  `[[/Engineering/Deploying]]` is from the top. Nothing is looked for elsewhere in the tree any more:
  `[[Deploying]]` no longer finds `engineering/deploying` from another page. Outside the wiki, as in a
  ticket, only links from the top are links. The API and MCP tools name a page by its whole address only.
  Not backwards compatible: a link written as the end of an address now names a page in the folder it is
  written in.
- The editor's writing help explains links to wiki pages in a part of their own, with plainer examples
  of each way to write one: by name, with words of your own, by the whole address, and from the page the
  link is in. The MCP tools and docs/wiki.md say the same.

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
