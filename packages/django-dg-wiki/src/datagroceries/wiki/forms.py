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
    """The page at `path`, an address a link named, under `parent`, the page above it, with the title the
    link gave it: neither is the starter's to choose, or the link would still lead nowhere. A title that
    gives another address is refused all the same; a page is renamed once it is there, and links follow."""

    title = forms.CharField(max_length=255, widget=forms.HiddenInput)

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
    return [('', _('No language set')), *choices] if blank else choices


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


class TopTextForm(forms.Form):
    """The wiki's own text, its start page. `original` is a fingerprint of what the editor started from, as
    on a page's form."""

    body = forms.CharField(
        label='', required=False, strip=False, widget=forms.Textarea(attrs={'data-markdown-editor': '', 'rows': 18})
    )
    original = forms.CharField(widget=forms.HiddenInput, required=False)


def top_fingerprint(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


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


def why_no_versions(page: Page):
    """Why `page` can have no versions in other languages, if it cannot: a folder, or no language of its own."""
    if page.folder:
        return _('A folder is in no language of its own, so it has no versions in other languages.')
    if not page.language:
        return _('Give this page a language first, on its edit page.')
    return None


class TranslateForm(forms.Form):
    """A new page beside `page`, in a language it is not in yet, starting from its text to translate."""

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
            # Not the page's own: two pages of a name cannot be in one folder.
            help_text=_('The title in that language.'),
            widget=forms.TextInput(attrs={'class': 'form-control'}),
        )
        self.page = page

    def clean(self):
        data = super().clean()
        if reason := why_no_versions(self.page):
            raise forms.ValidationError(reason)
        if 'title' in data:
            Page(title=data['title'], parent=self.page.parent).clean()
        return data


class LinkForm(forms.Form):
    """A page that is already there, in a language `page` is not in yet, and linked to no others, to make a
    version of it; with `user`, one they may read."""

    def __init__(self, *args, page: Page, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        taken = {each.language for each in page.translation_group()}
        pages = Page.objects.all() if user is None else access.pages(user)
        candidates = (
            pages.filter(folder=False, original=None, translations=None)
            .exclude(language='')
            .exclude(language__in=taken)
            .exclude(pk=page.pk)
            .order_by('path')
        )
        self.fields['other'] = forms.ModelChoiceField(
            candidates,
            label=_('Page'),
            empty_label=None,
            widget=forms.Select(attrs={'class': 'form-select'}),
        )
        self.fields['other'].label_from_instance = lambda each: f'{each.title} · /{each.path} · {each.language}'
        self.page = page

    def clean(self):
        data = super().clean()
        if reason := why_no_versions(self.page):
            raise forms.ValidationError(reason)
        return data
