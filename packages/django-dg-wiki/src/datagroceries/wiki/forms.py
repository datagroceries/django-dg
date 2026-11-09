import hashlib
import typing

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from datagroceries.wiki import access
from datagroceries.wiki.models import TOP, Comment, Page, flatten, slug_of


def fingerprint(page: Page) -> str:
    """What a page says, title and text, in short: what an edit started from."""
    return hashlib.sha256(f'{page.title}\n{page.body}'.encode()).hexdigest()


class PlaceField(forms.ModelChoiceField):
    """Where in the tree a page goes: in a folder, shown as the tree, or at the top; with `user`, only where
    they may write (datagroceries.wiki.access)."""

    def __init__(self, *, user=None, exclude: Page | None = None, **kwargs):
        # Only into a folder.
        pages = Page.objects.filter(folder=True)
        if exclude is not None:
            pages = pages.exclude(pk=exclude.pk).exclude(path__startswith=f'{exclude.path}/')
        if user is None:
            tree, at_top = pages.tree(), True
        else:
            pages = pages.filter(pk__in=access.writable(user))
            tree, at_top = access.tree(user), access.may(user, access.WRITE, TOP)
        super().__init__(
            queryset=pages,
            required=not at_top,
            empty_label=_('At the top') if at_top else None,
            label=_('Under'),
            widget=forms.Select(attrs={'class': 'form-select'}),
            **kwargs,
        )
        # In tree order, indented, rather than the queryset's order of position alone.
        allowed = set(pages.values_list('pk', flat=True))
        self.choices = ([('', self.empty_label)] if at_top else []) + [
            (page.pk, '\N{EM SPACE}' * depth + page.title) for page, depth in flatten(tree) if page.pk in allowed
        ]


class NewPageForm(forms.Form):
    """A new page starts from its title alone; its text is written after. With `user`, it goes only where
    they may write."""

    title = forms.CharField(
        label=_('Title'), max_length=255, widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'] = PlaceField(user=user)

    def clean(self):
        data = super().clean()
        if 'title' in data:
            Page(title=data['title'], parent=data.get('parent')).clean()
        return data


class StartPageForm(forms.Form):
    """The page at `path`, an address a link named, under `parent`, the page above it: its place is the
    address, so only a title that gives the same address will do, or the link would still lead nowhere."""

    title = forms.CharField(
        label=_('Title'), max_length=255, widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True})
    )

    def __init__(self, *args, path: str, parent: Page | None, **kwargs):
        super().__init__(*args, **kwargs)
        self.slug = path.rpartition('/')[2]
        self.parent = parent

    def clean_title(self):
        title = self.cleaned_data['title']
        if slug_of(title) != self.slug:
            raise forms.ValidationError(
                _(
                    'That title gives the page another address, so the link would still lead nowhere. '
                    'To start a page by another name, use “New page”.'
                )
            )
        return title

    def clean(self):
        data = super().clean()
        if 'title' in data:
            Page(title=data['title'], parent=self.parent).clean()
        return data


def _languages(blank: bool = True, leave_out=()) -> list:
    choices = [(code, name) for code, name in settings.LANGUAGES if code not in leave_out]
    return [('', _('No language said')), *choices] if blank else choices


class PageForm(forms.ModelForm):
    """The title and the text. `original` is the fingerprint of what the editor started from, so a save
    can be refused when somebody else saved the page meanwhile."""

    original = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Page
        fields = ('title', 'body', 'language')
        widgets: typing.ClassVar = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-lg'}),
            'body': forms.Textarea(attrs={'data-markdown-editor': '', 'rows': 24}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['body'].label = ''
        self.fields['language'] = forms.ChoiceField(
            choices=_languages(),
            required=False,
            label=_('Language'),
            widget=forms.Select(attrs={'class': 'form-select'}),
        )
        self.initial.setdefault('original', fingerprint(self.instance))


class MoveForm(forms.Form):
    def __init__(self, *args, page: Page, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.fields['parent'] = PlaceField(user=user, exclude=page, initial=page.parent_id)

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


class TranslateForm(forms.Form):
    """A translation of `page` into a language it is not in yet."""

    def __init__(self, *args, page: Page, **kwargs):
        super().__init__(*args, **kwargs)
        taken = {each.language for each in page.translation_group()}
        self.fields['language'] = forms.ChoiceField(
            choices=_languages(blank=False, leave_out=taken),
            label=_('Language'),
            widget=forms.Select(attrs={'class': 'form-select'}),
        )
        self.fields['title'] = forms.CharField(
            label=_('Title'),
            max_length=255,
            initial=page.title,
            help_text=_('The title in that language.'),
            widget=forms.TextInput(attrs={'class': 'form-control'}),
        )
        self.page = page

    def clean(self):
        data = super().clean()
        if 'title' in data:
            Page(title=data['title'], parent=self.page.parent).clean()
        return data
