import hashlib
import typing

from django import forms
from django.utils.translation import gettext_lazy as _

from gilde.wiki.models import Comment, Page, flatten


def fingerprint(page: Page) -> str:
    """What a page says, title and text, in short: what an edit started from."""
    return hashlib.sha256(f'{page.title}\n{page.body}'.encode()).hexdigest()


class PlaceField(forms.ModelChoiceField):
    """Where in the tree a page goes: under one of `pages`, shown as the tree, or at the top."""

    def __init__(self, *, exclude: Page | None = None, **kwargs):
        pages = Page.objects.all()
        if exclude is not None:
            pages = pages.exclude(pk=exclude.pk).exclude(path__startswith=f'{exclude.path}/')
        super().__init__(
            queryset=pages,
            required=False,
            empty_label=_('At the top'),
            label=_('Under'),
            widget=forms.Select(attrs={'class': 'form-select'}),
            **kwargs,
        )
        # In tree order, indented, rather than the queryset's order of position alone.
        self.choices = [('', self.empty_label)] + [
            (page.pk, '\N{EM SPACE}' * depth + page.title) for page, depth in flatten(pages.tree())
        ]


class NewPageForm(forms.Form):
    """A new page starts from its title alone; its text is written after."""

    title = forms.CharField(
        label=_('Title'), max_length=255, widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'] = PlaceField()

    def clean(self):
        data = super().clean()
        if 'title' in data:
            Page(title=data['title'], parent=data.get('parent')).clean()
        return data


class PageForm(forms.ModelForm):
    """The title and the text. `original` is the fingerprint of what the editor started from, so a save
    can be refused when somebody else saved the page meanwhile."""

    original = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Page
        fields = ('title', 'body')
        widgets: typing.ClassVar = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-lg'}),
            'body': forms.Textarea(attrs={'data-markdown-editor': '', 'rows': 24}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['body'].label = ''
        self.initial.setdefault('original', fingerprint(self.instance))


class MoveForm(forms.Form):
    def __init__(self, *args, page: Page, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.fields['parent'] = PlaceField(exclude=page, initial=page.parent_id)

    def clean(self):
        data = super().clean()
        moved = Page.objects.get(pk=self.page.pk)
        moved.parent = data.get('parent')
        moved.clean()
        return data


class ArrangeForm(forms.Form):
    """A page dragged in the tree: under `parent`, or at the top, before `before`, or after the pages
    there."""

    page = forms.ModelChoiceField(Page.objects.all())
    parent = forms.ModelChoiceField(Page.objects.all(), required=False)
    before = forms.ModelChoiceField(Page.objects.all(), required=False)

    def clean(self):
        data = super().clean()
        page, parent, before = data.get('page'), data.get('parent'), data.get('before')
        if page is None:
            return data
        if before is not None and (before == page or before.parent_id != (parent.pk if parent else None)):
            raise forms.ValidationError(_('That place is not in the tree.'))
        moved = Page.objects.get(pk=page.pk)
        moved.parent = parent
        moved.clean()
        return data


class CommentForm(forms.ModelForm):
    """A comment on `page`, or a reply to one of its comments (`parent`)."""

    class Meta:
        model = Comment
        fields = ('body', 'parent')
        widgets: typing.ClassVar = {
            'body': forms.Textarea(
                attrs={'data-markdown-editor': 'true', 'rows': 4, 'placeholder': _('Leave a comment.')}
            ),
            'parent': forms.HiddenInput,
        }

    def __init__(self, *args, page: Page, **kwargs):
        super().__init__(*args, instance=Comment(page=page), **kwargs)
        self.fields['body'].label = ''
        self.fields['parent'].queryset = page.comments.filter(parent=None)
