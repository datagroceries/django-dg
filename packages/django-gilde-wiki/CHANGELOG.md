# Changelog of django-gilde-wiki

## Unreleased

- Pages in one tree, at addresses that follow it, read with a table of contents, written in core's
  Markdown editor; renamed, moved and deleted, with the old addresses still leading to their page. Every
  save kept in the history, and a save refused when someone else saved first.
- Links between pages, "[[Engineering/Deploying]]", in the wiki and in every Gilde app's Markdown, by the
  end of an address, the whole of it ("[[/Engineering/Deploying]]"), or in a page from that page
  ("[[./Rollback]]", "[[../Onboarding]]"); a link to no page shown as one, offering to start it. A page
  lists the pages that link to it, and links follow a page that is renamed or moved, and relative ones
  the page they are in.
- Pages put in order, or under another page, by dragging them in the tree.
- A page's history: every version with who made it and what it changed, two versions side by side with
  the changed words marked, and an earlier version brought back as a new one.
- Images pasted or dropped into the editor, and files put beside a page, served only to the wiki's
  people. A page with only pages under it shows them, as an index would.
- Comments on a page, and replies to them, written in the editor with @-mentions; watchers hear about new
  comments, and the people mentioned in a page or a comment hear about it.
- Search through the pages' titles and texts. A page, or a page with all under it, or the whole wiki,
  downloaded as Markdown, with its images and the links between the pages kept.
- A language per page, and translations beside it that link to each other and say when the page they
  translate changed after them.
- A REST API and MCP tools for everything the pages do but uploading files and downloading: finding,
  reading, writing, moving and deleting pages, their history, comments, watching and translations. A
  change to a page's text may say the version it started from, and is refused when the page changed
  since.
- A ticket lists the wiki pages that name its key, while the board is installed too.
