# Changelog of django-gilde-wiki

## Unreleased

- Pages in one tree, at addresses that follow it, read with a table of contents, written in core's
  Markdown editor; renamed, moved and deleted, with the old addresses still leading to their page. Every
  save kept in the history, and a save refused when someone else saved first.
- Links between pages, "[[Engineering/Deploying]]", in the wiki and in every Gilde app's Markdown, a link
  to no page shown as one, offering to start it. A page lists the pages that link to it, and links follow
  a page that is renamed or moved.
- Pages put in order, or under another page, by dragging them in the tree.
