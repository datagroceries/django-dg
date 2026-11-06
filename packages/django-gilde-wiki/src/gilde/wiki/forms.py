import hashlib
import typing

from django import forms
from django.utils.translation import gettext_lazy as _

from gilde.wiki.models import Page, flatten


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
