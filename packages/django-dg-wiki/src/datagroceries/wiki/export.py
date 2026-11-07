"""Pages as Markdown files, to read or keep outside the wiki.

One page is one file, its title as its first heading. A page with pages under it comes as a zip of the
page and everything under it, each at its address with ".md" after it ("engineering/deploying.md") and its
files beside it ("engineering/deploying.files/screenshot.png"). Links between the pages in the zip become
ordinary links between the files; a link to a page outside it, or to a file, is the wiki's address of it.
A link to no page is its text.
"""

import io
import posixpath
import re
import zipfile

from django.urls import reverse

from datagroceries.wiki import links
from datagroceries.wiki.models import Attachment, Page


def _file_re():
    # A file's address on the wiki, as the editor puts it in the text: /dg/wiki/-/files/12/name.png
    prefix = reverse('dg_wiki:attachment', args=[0, 'name']).removesuffix('0/name')
    return re.compile(rf'(?:https?://[^/\s]+)?{re.escape(prefix)}(\d+)/[^\s)"\'<>]+')


def page_markdown(request, page: Page, *, files: dict | None = None, inside: dict | None = None) -> str:
    """The page as one Markdown file. `inside` are the other files exported with it, by page id, and
    `files` the attachments exported, by id: their links are relative to this one's file."""
    files, inside = files or {}, inside or {}
    here = posixpath.dirname(inside.get(page.pk, ''))

    def address(path: str) -> str:
        return request.build_absolute_uri(path)

    def relative(path: str) -> str:
        return posixpath.relpath(path, here or '.')

    found = links.resolve({links.reference(match[1], page.path) for match in links.matches(page.body)})

    def link(match):
        written, label = match.groups()
        target = found.get(links.reference(written, page.path))
        text = (label or '').strip() or (target.title if target else written.split('/')[-1].strip())
        if target is None:
            return text
        url = relative(inside[target.pk]) if target.pk in inside else address(target.get_absolute_url())
        return f'[{text}]({url})'

    def file(match):
        pk = int(match[1])
        if pk in files:
            return relative(files[pk])
        return address(match[0]) if match[0].startswith('/') else match[0]

    body = links.substitute(page.body, link)
    body = _file_re().sub(file, body)
    return f'# {page.title}\n\n{body.strip()}\n'


def tree_zip(request, top: Page | None) -> bytes:
    """`top` and every page under it, or the whole wiki, as a zip of Markdown files and their files."""
    pages = [top, *top.descendants()] if top else list(Page.objects.all())
    # Under the zip's root, from `top`'s own address on: "deploying.md", "deploying/rollback.md".
    start = len(top.path) - len(top.slug) if top else 0
    inside = {page.pk: f'{page.path[start:]}.md' for page in pages}
    attachments = list(Attachment.objects.filter(page__in=pages))
    files = {}
    for attachment in attachments:
        folder = inside[attachment.page_id].removesuffix('.md') + '.files'
        files[attachment.pk] = f'{folder}/{attachment.pk}-{attachment.url_name}'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for page in pages:
            archive.writestr(inside[page.pk], page_markdown(request, page, files=files, inside=inside))
        for attachment in attachments:
            with attachment.file.open('rb') as content:
                archive.writestr(files[attachment.pk], content.read())
    return buffer.getvalue()
