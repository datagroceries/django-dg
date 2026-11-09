"""The wiki's REST API: read and change pages as the person whose token it is, or through the wiki's MCP
tools (datagroceries.wiki.mcp), which run these views.

Changes go through datagroceries.wiki.operations, like the pages, and are checked by the pages' own forms, so the
rules, who may make them (datagroceries.wiki.access) and the notifications are the same. A page the person may
not read is not found. A page is named by its address, or by what a link to it would
say ("Engineering/Deploying", "deploying"). A change to a page's title or text may say the version it
started from, and is refused when the page changed since, as on the pages.
"""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.html import strip_tags
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from datagroceries.core.api import form_errors, person, validated
from datagroceries.core.authentication import DataGroceriesAuthentication, HasTokenScope
from datagroceries.wiki import access, links, notifications, operations, search, versions
from datagroceries.wiki.access import WRITE
from datagroceries.wiki.conf import SCOPE
from datagroceries.wiki.forms import ArrangeForm, CommentForm, NewPageForm, TranslateForm
from datagroceries.wiki.models import TOP, Page, flatten

LIST_LIMIT = 200
MAX_LIST_LIMIT = 1000


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'The page changed since the version this change started from.'


class PageFieldsSerializer(serializers.Serializer):
    """The fields a page is created or changed with; only the ones sent are applied."""

    title = serializers.CharField(max_length=255)
    body = serializers.CharField(allow_blank=True, trim_whitespace=False)
    language = serializers.CharField(allow_blank=True, max_length=10)
    parent = serializers.CharField(allow_blank=True, allow_null=True)
    before = serializers.CharField(allow_blank=True, allow_null=True)
    version = serializers.IntegerField()

    def validate_language(self, value):
        if value and value not in dict(settings.LANGUAGES):
            raise serializers.ValidationError(f'One of {", ".join(dict(settings.LANGUAGES))}, or empty.')
        return value


class PageCreateSerializer(PageFieldsSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ('before', 'version'):
            del self.fields[field]
        for name, field in self.fields.items():
            field.required = name == 'title'


class CommentSerializer(serializers.Serializer):
    body = serializers.CharField()
    parent = serializers.IntegerField(required=False, help_text='The id of the comment this replies to.')


class CommentEditSerializer(serializers.Serializer):
    body = serializers.CharField(help_text='The whole new text, Markdown.')


class TranslateSerializer(serializers.Serializer):
    language = serializers.CharField()
    title = serializers.CharField(max_length=255)


def _find(request, path: str | None, queryset=None) -> Page | None:
    """The page `path` names, as a link to it would, among those the person may read; None for an empty
    one, which is the top."""
    if not path or not path.strip('/'):
        return None
    name = links.reference(path.strip().rstrip('/'))
    found = links.resolve({name}).get(name) if name else None
    readable = access.pages(request.user, queryset if queryset is not None else Page.objects.all())
    page = readable.filter(pk=found.pk).first() if found else None
    if page is None and found is not None and not name.startswith('/'):
        # The end of an address names the highest page so ending; when that one is hidden, a page the
        # person may read that ends so.
        ends = readable.filter(path__endswith=f'/{name}') | readable.filter(path=name)
        page = min(ends, key=lambda each: (each.path.count('/'), each.path), default=None)
    if page is None:
        raise NotFound(f'No page {path}.')
    return page


def _summary(page: Page) -> dict:
    return {'path': page.path, 'title': page.title}


def _comment(comment) -> dict:
    return {
        'id': comment.pk,
        'author': person(comment.author),
        'body': comment.body,
        'created_at': comment.created_at,
    }


def _detail(request, page: Page) -> dict:
    last = page.history.select_related('history_user').first()
    readable, hidden = access.pages(request.user), access.hidden(request.user)
    comments = page.comments.filter(parent=None).select_related('author').prefetch_related('replies__author')
    return {
        **_summary(page),
        'url': request.build_absolute_uri(page.get_absolute_url()),
        'language': page.language,
        'body': page.body,
        'version': last.history_id,
        'last_changed': {
            'by': person(versions.changed_by(page, last)),
            'at': last.history_date,
            'via': (last.history_change_reason or '').removeprefix('via ') or None,
        },
        'parent': page.parent.path if page.parent else None,
        'children': [_summary(child) for child in readable.filter(parent=page)],
        'original': page.original.path if page.original and page.original.pk not in hidden else None,
        'translations': [
            {**_summary(each), 'language': each.language}
            for each in page.translation_group()
            if each.pk != page.pk and each.pk not in hidden
        ],
        'linked_from': [_summary(each) for each in readable.filter(links__target=page).exclude(pk=page.pk).distinct()],
        'attachments': [
            {'name': attachment.name, 'url': request.build_absolute_uri(attachment.get_absolute_url())}
            for attachment in page.attachments.all()
        ],
        'comments': [
            {**_comment(each), 'replies': [_comment(reply) for reply in each.replies.all()]} for each in comments
        ],
        'watchers': [
            person(user)
            for user in access.readers(page, [watcher.user for watcher in page.watchers.select_related('user')])
        ],
    }


def _place(request, page: Page, data: dict):
    """Put the page where `data` says: under `parent`, before `before`; checked as dragging it is."""
    if 'parent' not in data and 'before' not in data:
        return
    parent = _find(request, data['parent']) if 'parent' in data else page.parent
    before = _find(request, data.get('before'))
    form = ArrangeForm({'page': page.pk, 'parent': parent.pk if parent else '', 'before': before.pk if before else ''})
    if not form.is_valid():
        raise form_errors(form)
    operations.arrange(request, page, parent, before)


class WikiApiView(DataGroceriesAuthentication, APIView):
    # The wiki's area (datagroceries.wiki.mcp.AREA) keeps it to the people who may use it (datagroceries.core.people).
    permission_classes = (HasTokenScope,)
    token_scope = SCOPE


class PageListCreateView(WikiApiView):
    def get(self, request):
        """With `q`, the pages holding every word, the best first; else the tree, in order, from the page
        `under` or the top."""
        params = request.query_params
        limit = min(int(params.get('limit', LIST_LIMIT)), MAX_LIST_LIMIT)
        if query := params.get('q', '').strip():
            hits = search.search(query, access.pages(request.user))
            results = [{**_summary(hit.page), 'snippet': strip_tags(hit.snippet)} for hit in hits]
            return Response({'count': len(results), 'results': results[:limit]})
        under = _find(request, params.get('under'))
        pages = access.pages(request.user, under.descendants() if under else None)
        results = [
            {**_summary(page), 'depth': depth, 'language': page.language} for page, depth in flatten(pages.tree())
        ]
        return Response({'count': len(results), 'results': results[:limit]})

    def post(self, request):
        data = validated(PageCreateSerializer, request)
        parent = _find(request, data.get('parent'))
        access.require(request.user, WRITE, parent or TOP)
        form = NewPageForm({'title': data['title'], 'parent': parent.pk if parent else ''})
        if not form.is_valid():
            raise form_errors(form)
        with transaction.atomic():
            page = operations.create(request, data['title'], parent, data.get('body', ''))
            if data.get('language'):
                Page.objects.filter(pk=page.pk).update(language=data['language'])
                page.language = data['language']
        return Response(_detail(request, page), status=status.HTTP_201_CREATED)


class PageDetailView(WikiApiView):
    def get(self, request, path):
        return Response(_detail(request, _find(request, path)))

    def patch(self, request, path):
        data = validated(PageFieldsSerializer, request, partial=True)
        with transaction.atomic():
            page = _find(request, path, Page.objects.select_for_update())
            texts = {field: data.get(field, getattr(page, field)) for field in ('title', 'body', 'language')}
            if any(texts[field] != getattr(page, field) for field in texts):
                latest = page.history.first().history_id
                if 'version' in data and data['version'] != latest:
                    raise Conflict(
                        f'The page changed since version {data["version"]}; it is at version {latest} now. '
                        'Read it again, put the two together, and send the change with the new version.'
                    )
                if texts['title'] != page.title:
                    form = NewPageForm({'title': texts['title'], 'parent': page.parent_id or ''})
                    if not form.is_valid():
                        raise form_errors(form)
                operations.write(request, page, texts['title'], texts['body'], texts['language'])
            _place(request, page, data)
        page.refresh_from_db()
        return Response(_detail(request, page))

    def delete(self, request, path):
        page = _find(request, path)
        try:
            operations.delete(request, page)
        except DjangoValidationError as error:
            raise ValidationError({'detail': error.messages}) from error
        return Response(status=status.HTTP_204_NO_CONTENT)


class PageHistoryView(WikiApiView):
    def get(self, request, path):
        """Every version of the page, newest first."""
        page = _find(request, path)
        return Response(
            [
                {
                    'version': version['record'].history_id,
                    'at': version['record'].history_date,
                    'by': person(version['by']),
                    'via': (version['record'].history_change_reason or '').removeprefix('via ') or None,
                    'changes': version['changes'],
                }
                for version in versions.of(page)
            ]
        )


class PageVersionView(WikiApiView):
    def _version(self, request, path, version):
        page = _find(request, path)
        record = page.history.filter(history_id=version).first()
        if record is None:
            raise NotFound(f'No version {version} of {page.path}.')
        return page, record

    def get(self, request, path, version):
        """What the page said in that version."""
        _page, record = self._version(request, path, version)
        return Response(
            {'version': record.history_id, 'title': record.title, 'body': record.body, 'at': record.history_date}
        )

    def post(self, request, path, version):
        """Bring that version back, as a new one."""
        page, record = self._version(request, path, version)
        operations.restore(request, page, record)
        page.refresh_from_db()
        return Response(_detail(request, page))


class PageCommentsView(WikiApiView):
    def post(self, request, path):
        data = validated(CommentSerializer, request)
        page = _find(request, path)
        form = CommentForm({'body': data['body'], 'parent': data.get('parent')}, page=page)
        if not form.is_valid():
            raise form_errors(form)
        made = operations.comment(request, page, form.cleaned_data['body'], form.cleaned_data['parent'])
        return Response(_comment(made), status=status.HTTP_201_CREATED)


class PageCommentView(WikiApiView):
    def patch(self, request, path, comment_id):
        """Change the text of a comment or reply, as its author does on the page: only the people it newly
        @-mentions hear about it."""
        page = _find(request, path)
        comment = page.comments.filter(pk=comment_id).first()
        if comment is None:
            raise NotFound(f'No comment {comment_id} on {page.path}.')
        if comment.author_id != request.user.pk:
            raise PermissionDenied('Only its author can edit a comment.')
        operations.edit_comment(request, comment, validated(CommentEditSerializer, request)['body'])
        return Response(_comment(comment))


class PageWatchView(WikiApiView):
    def post(self, request, path):
        """Start watching the page."""
        page = _find(request, path)
        notifications.watch(page, request.user)
        return Response(_detail(request, page))

    def delete(self, request, path):
        """Stop watching the page."""
        page = _find(request, path)
        page.watchers.filter(user=request.user).delete()
        return Response(_detail(request, page))


class PageTranslationsView(WikiApiView):
    def post(self, request, path):
        """A translation of the page, beside it, starting from its text."""
        data = validated(TranslateSerializer, request)
        page = _find(request, path)
        form = TranslateForm(data, page=page)
        if not form.is_valid():
            raise form_errors(form)
        made = operations.translate(request, page, form.cleaned_data['language'], form.cleaned_data['title'])
        return Response(_detail(request, made), status=status.HTTP_201_CREATED)
