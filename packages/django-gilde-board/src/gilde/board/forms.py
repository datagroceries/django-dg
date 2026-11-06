import hashlib
import json
import typing

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from gilde.board.conf import SCOPE
from gilde.board.models import KEY_RE, Column, Comment, Group, Label, Relation, Ticket
from gilde.core import people


class PersonChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return people.name(obj)


def column_choices() -> list[tuple[str, list[tuple[int, str]]]]:
    """Every column, grouped per group: picking a column of another group moves the ticket there."""
    choices: dict[str, list[tuple[int, str]]] = {}
    for column in Column.objects.select_related('group'):
        choices.setdefault(column.group.name, []).append((column.pk, column.name))
    return list(choices.items())


class TicketForm(forms.ModelForm):
    column = forms.TypedChoiceField(coerce=int, label=gettext_lazy('Group / column'))
    labels_text = forms.CharField(
        required=False,
        label=gettext_lazy('Labels'),
        help_text=gettext_lazy('Pick a label, or type a new name and press Enter.'),
    )

    class Meta:
        model = Ticket
        fields = ('title', 'description', 'assignee', 'size')
        field_classes: typing.ClassVar = {'assignee': PersonChoiceField}
        widgets: typing.ClassVar = {
            'description': forms.Textarea(
                attrs={
                    'data-markdown-editor': 'true',
                    'rows': 12,
                    'placeholder': gettext_lazy('Describe the ticket (Markdown).'),
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['column'].choices = column_choices()
        self.fields['assignee'].queryset = people.members(SCOPE)
        self.fields['assignee'].widget.attrs['data-tk-select'] = ''
        self.fields['assignee'].empty_label = _('Unassigned')
        self.fields['column'].widget.attrs['data-tk-select'] = ''
        self.fields['size'].choices = [('', _('Not estimated')), *Ticket.Size.choices]
        self.fields['labels_text'].widget.attrs.update(
            {'data-tk-labels': '', 'data-options': json.dumps(list(Label.objects.values_list('name', flat=True)))},
        )

    def clean_column(self):
        return Column.objects.get(pk=self.cleaned_data['column'])

    def clean_labels_text(self):
        names = {name.strip() for name in self.cleaned_data['labels_text'].split(',')}
        return sorted(name for name in names if name)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class TicketTextForm(forms.Form):
    """Edits one text field of a ticket in place.

    `original` is a fingerprint of the text the editor started from, so a save can be refused when
    somebody else changed that same text meanwhile. Changes to other fields never get in the way.
    """

    field_name: typing.ClassVar[str]
    original = forms.CharField(widget=forms.HiddenInput)

    @classmethod
    def for_ticket(cls, ticket: Ticket, data=None):
        value = getattr(ticket, cls.field_name)
        return cls(data, initial={cls.field_name: value, 'original': fingerprint(value)})


class TitleForm(TicketTextForm):
    field_name = 'title'
    title = forms.CharField(max_length=255, widget=forms.TextInput(attrs={'class': 'form-control tk-title-input'}))


class DescriptionForm(TicketTextForm):
    field_name = 'description'
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                'data-markdown-editor': 'lazy',
                'rows': 12,
                'placeholder': gettext_lazy('Describe the ticket (Markdown).'),
            },
        ),
    )


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ('body', 'parent')
        widgets: typing.ClassVar = {
            'body': forms.Textarea(
                attrs={
                    'data-markdown-editor': 'true',
                    'rows': 4,
                    'placeholder': gettext_lazy('Leave a comment. Paste an image to attach it.'),
                },
            ),
            'parent': forms.HiddenInput,
        }


class BlockForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)

    def __init__(self, *args, ticket: Ticket, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket = ticket
        self.fields['reason'].label = 'Why is it unblocked?' if ticket.is_blocked else 'Why is it blocked?'

    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if not self.ticket.is_blocked and not reason:
            raise ValidationError(_('Say why the ticket is blocked.'))
        return reason


class RelationForm(forms.Form):
    """Adds a relation as read from this ticket's side; the reversed kinds swap source and target."""

    KINDS: typing.ClassVar = {
        'parent_of': (Relation.Type.PARENT_OF, False),
        'child_of': (Relation.Type.PARENT_OF, True),
        'blocks': (Relation.Type.BLOCKS, False),
        'blocked_by': (Relation.Type.BLOCKS, True),
        'duplicate_of': (Relation.Type.DUPLICATE_OF, False),
        'duplicated_by': (Relation.Type.DUPLICATE_OF, True),
        'relates_to': (Relation.Type.RELATES_TO, False),
    }

    kind = forms.ChoiceField(
        # Named as the ticket page names relations, in the reader's language.
        choices=[
            (kind, Relation.INVERSE_LABELS[type_] if reverse else type_.label)
            for kind, (type_, reverse) in KINDS.items()
        ],
        widget=forms.Select(attrs={'class': 'form-select flex-grow-0 w-auto'}),
    )
    other = forms.CharField(
        label=gettext_lazy('Ticket'),
        widget=forms.TextInput(attrs={'placeholder': f'{settings.GILDE_BOARD_KEY_PREFIX}-123'}),
    )

    def __init__(self, *args, ticket: Ticket, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket = ticket

    def clean_other(self):
        match = KEY_RE.match(self.cleaned_data['other'].strip().upper())
        if not match or not Ticket.objects.filter(pk=int(match[1])).exists():
            raise ValidationError(_('No such ticket.'))
        return Ticket.objects.get(pk=int(match[1]))

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        relation_type, reversed_ = self.KINDS[cleaned['kind']]
        source, target = (cleaned['other'], self.ticket) if reversed_ else (self.ticket, cleaned['other'])
        self.relation = Relation(source=source, target=target, type=relation_type)
        self.relation.full_clean()
        return cleaned


class ChildForm(forms.Form):
    """Creates a new ticket as a child of the ticket whose page it is on, from just a title."""

    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm', 'placeholder': gettext_lazy('New child ticket')}
        ),
    )


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ('name', 'slug', 'position', 'done_days')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['slug'].help_text = 'Used in the board URL. Left empty, it is made from the name.'

    def clean_slug(self):
        slug = self.cleaned_data['slug'] or slugify(self.cleaned_data.get('name', ''))
        if slug == 'new':
            raise ValidationError(_('"new" is the address of the page for a new group; choose another slug.'))
        return slug


class BaseColumnFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.deleted_forms:
            if form.instance.pk and form.instance.tickets.exists():
                raise ValidationError(
                    _('Column "%(name)s" still holds tickets; move them out first.') % {'name': form.instance.name}
                )
        if not [form for form in self.forms if form.cleaned_data and not form.cleaned_data.get('DELETE')]:
            raise ValidationError(_('A group needs at least one column.'))


ColumnFormSet = forms.inlineformset_factory(
    Group,
    Column,
    formset=BaseColumnFormSet,
    fields=('name', 'category', 'position'),
    extra=1,
    can_delete=True,
)
