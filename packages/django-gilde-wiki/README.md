# django-gilde-wiki

A wiki for a Django project, that people and AI agents write together, next to the board. Part of
[Gilde](https://github.com/gildehq/gilde).

## What it does

- Pages in Markdown, in one tree: a page with pages under it is what elsewhere is a space or a folder.
  Addresses follow the tree (`gilde/wiki/engineering/deploying/`), and a page renamed or moved keeps its
  old address leading to it. Pages are put in order, or under another, by dragging them in the tree.
- Links between pages, `[[Engineering/Deploying]]`, also from a ticket's text. A page lists the pages
  that link to it, and the links follow it when it is renamed or moved.
- The Markdown editor of every Gilde app, and a table of contents beside a long page.
- Every save kept, with who made it and through which agent; two versions compared side by side, and an
  earlier one brought back. A save is refused when someone else saved the page in the meantime.
- Images in the text, pasted or dropped into the editor, and files beside a page.
- English and Dutch, following the project's language.

It is being built: comments, search, translations, the board's
tickets and the MCP tools follow.

## Installing

As every Gilde app, described in
[docs/integrating.md](https://github.com/gildehq/gilde/blob/main/docs/integrating.md): add `'gilde.wiki'`
to `INSTALLED_APPS` after `'gilde.core'`, run `manage.py migrate`, and grant the permission "Can use the
wiki" (`gilde_wiki.use`) to a group. The pages are at `gilde/wiki/`.

MIT licensed.
