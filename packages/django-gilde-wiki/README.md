# django-gilde-wiki

A wiki for a Django project, that people and AI agents write together, next to the board. Part of
[Gilde](https://github.com/gildehq/gilde).

## What it does

- Pages in Markdown, in one tree: a page with pages under it is what elsewhere is a space or a folder.
  Addresses follow the tree (`gilde/wiki/engineering/deploying/`), and a page renamed or moved keeps its
  old address leading to it. Pages are put in order, or under another, by dragging them in the tree.
- Links between pages, `[[Engineering/Deploying]]`, also from a ticket's text: by the end of an address
  (`[[Deploying]]`), the whole of it (`[[/Engineering/Deploying]]`), or from the page they are in, as in
  a folder (`[[./Rollback]]` under it, `[[../Onboarding]]` beside it). A page lists the pages that link to
  it, and the links follow when a page is renamed or moved.
- The Markdown editor of every Gilde app, and a table of contents beside a long page.
- Every save kept, with who made it and through which agent; two versions compared side by side, and an
  earlier one brought back. A save is refused when someone else saved the page in the meantime.
- Images in the text, pasted or dropped into the editor, and files beside a page.
- Comments and replies, with @-mentions; the people watching a page hear about new comments.
- Search through every page's title and text, and pages downloaded as Markdown: one page as a file, or
  a page with all under it, or the whole wiki, as a zip with their images, the links between them kept.
- A page in several languages: each translation beside it, linked to the others, and told when the page
  it translates changed after it.
- A REST API and MCP tools for everything the pages do but uploading and downloading files, and on a
  ticket, while the board is installed too, the wiki pages that name it.
- English and Dutch, following the project's language.

## Installing

As every Gilde app, described in
[docs/integrating.md](https://github.com/gildehq/gilde/blob/main/docs/integrating.md): add `'gilde.wiki'`
to `INSTALLED_APPS` after `'gilde.core'`, run `manage.py migrate`, and grant the permission "Can use the
wiki" (`gilde_wiki.use`) to a group. The pages are at `gilde/wiki/`.

MIT licensed.
