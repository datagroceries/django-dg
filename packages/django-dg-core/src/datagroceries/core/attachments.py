"""Files people attach, as every DataGroceries app keeps them: each app has a table of its own, on `Attachment`,
saying what a file belongs to, and serves the files with `serve`, only to those who may use the app.

Images pasted or dropped into the Markdown editor go to the app's upload address, which answers with
`editor_upload`.
"""

import pathlib

from django.conf import settings
from django.db import models
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.utils.text import slugify

MAX_BYTES = 20 * 1024 * 1024
# What is shown in the page; anything else is a download.
INLINE_CONTENT_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')


def upload_to(attachment, filename: str) -> str:
    return f'{attachment._meta.app_label}/{timezone.now():%Y/%m}/{filename}'


class Attachment(models.Model):
    """A file, in the default storage. The app serves it only to its people (`serve`), so the storage must
    not publish it at an address of its own."""

    INLINE_CONTENT_TYPES = INLINE_CONTENT_TYPES

    file = models.FileField(upload_to=upload_to)
    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ('uploaded_at', 'id')

    def __str__(self):
        return self.name

    @property
    def is_image(self) -> bool:
        return self.content_type in INLINE_CONTENT_TYPES

    @property
    def url_name(self) -> str:
        """The file's name for the end of its address. The Markdown editor inserts an upload as an image only
        when its address ends in an image extension; slugified, so no space or bracket breaks a link."""
        path = pathlib.PurePath(self.name)
        return f'{slugify(path.stem) or "file"}{path.suffix.lower()}'

    @classmethod
    def from_upload(cls, upload, user, **fields):
        """A new attachment of the uploaded file, by `user`, with the app's own `fields`."""
        return cls.objects.create(
            file=upload,
            name=upload.name,
            content_type=upload.content_type or 'application/octet-stream',
            size=upload.size,
            uploaded_by=user,
            **fields,
        )


def serve(attachment: Attachment) -> FileResponse:
    """The file. Only known image types are shown inline; anything else (HTML, SVG, ...) is a download, so
    an uploaded file can never run as a page on this site."""
    response = FileResponse(
        attachment.file.open('rb'),
        content_type=attachment.content_type if attachment.is_image else 'application/octet-stream',
        as_attachment=not attachment.is_image,
        filename=attachment.name,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def editor_upload(request, create) -> JsonResponse:
    """The answer to an image the Markdown editor uploads, in the form EasyMDE expects. `create(upload)`
    keeps the image and returns its Attachment."""
    upload = request.FILES.get('image')
    if upload is None:
        return JsonResponse({'error': 'noFileGiven'}, status=400)
    if upload.size > MAX_BYTES:
        return JsonResponse({'error': 'fileTooLarge'}, status=400)
    if upload.content_type not in INLINE_CONTENT_TYPES:
        return JsonResponse({'error': 'typeNotAllowed'}, status=400)
    return JsonResponse({'data': {'filePath': create(upload).get_absolute_url()}})
