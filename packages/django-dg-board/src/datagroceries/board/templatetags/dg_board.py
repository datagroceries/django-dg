import zlib

from django import forms, template
from django.conf import settings
from django.forms.formsets import BaseFormSet
from django.utils.html import format_html
from django.utils.translation import gettext as _

from datagroceries.board import access
from datagroceries.board.conf import SCOPE
from datagroceries.core import mentions, people

register = template.Library()

CATEGORY_ICONS = {
    'todo': 'bi-circle',
    'in_progress': 'bi-circle-half',
    'done': 'bi-check-circle-fill',
}


@register.simple_tag
def tracker_name() -> str:
    return settings.DG_BOARD_NAME


@register.simple_tag
def mention_people(ticket=None):
    """The colleagues an @-mention reaches, as JSON for the editor's autocomplete: each with the handle that
    reaches them, as notifications.mentioned_users reads it, and on a ticket whether they can see it."""
    return mentions.people_json(SCOPE, access.visible_to(ticket.column.group) if ticket else None)


@register.filter
def person(user, fallback: str = '—') -> str:
    """A user's name; `fallback` when there is no user."""
    if user is None:
        return fallback
    return people.name(user)


@register.filter
def person_short(user) -> str:
    """What a small card has room for of a user's name."""
    return people.short_name(user)


@register.simple_tag
def ticket_theme():
    """The tracker's colours as CSS variables, from settings.DG_BOARD_COLORS."""
    colors = settings.DG_BOARD_COLORS
    variables = ''.join(f'--tk-{name.replace("_", "-")}: {colors[name]};' for name in CATEGORY_ICONS)
    variables += ''.join(f'--tk-accent-{index}: {color};' for index, color in enumerate(colors['accents']))
    return format_html('<style>:root {{ {} --tk-blocked: {}; }}</style>', variables, colors['blocked'])


def _accent(seed: str) -> str:
    accents = settings.DG_BOARD_COLORS['accents']
    return accents[zlib.crc32(seed.encode()) % len(accents)]


@register.simple_tag
def avatar(user, size: str = 'sm'):
    """The user's image, when the host project has one (datagroceries.core.people.avatar_url), else their
    initials in an accent colour that stays the same per user."""
    if user is None:
        return format_html(
            '<span class="tk-avatar tk-avatar-{} tk-avatar-empty" title="{}"></span>', size, _('Unassigned')
        )
    name = people.name(user)
    # 64 px covers the largest avatar (2rem) on a high-density screen.
    if photo := people.avatar_url(user, 64):
        return format_html('<img class="tk-avatar tk-avatar-{}" src="{}" alt="" title="{}">', size, photo, name)
    initials = ''.join(part[0] for part in name.replace('@', ' ').split()[:2]).upper()
    return format_html(
        '<span class="tk-avatar tk-avatar-{}" style="background: {}" title="{}">{}</span>',
        size,
        _accent(str(user.pk)),
        name,
        initials,
    )


@register.filter
def label_color(label) -> str:
    return _accent(str(label))


@register.filter
def category_icon(category: str) -> str:
    return CATEGORY_ICONS[category]


@register.inclusion_tag('dg_board/_field.html')
def field(bound_field, label: bool = True, help_text: bool = True) -> dict:
    """A form field as Bootstrap lays it out: label, widget, errors and help text. Without `label` the label
    is for screen readers only, and a text field says what it is in its placeholder instead."""
    widget = bound_field.field.widget
    checkbox = isinstance(widget, forms.CheckboxInput)
    kind = 'form-check-input' if checkbox else 'form-select' if isinstance(widget, forms.Select) else 'form-control'
    classes = widget.attrs.get('class', '').split()
    classes += [kind] if kind not in classes else []
    classes += ['is-invalid'] if bound_field.errors else []
    attrs = {'class': ' '.join(classes)}
    if not label and isinstance(widget, forms.widgets.Input) and not checkbox and 'placeholder' not in widget.attrs:
        attrs['placeholder'] = bound_field.label
    return {
        'field': bound_field,
        'widget': bound_field.as_widget(attrs=attrs),
        'checkbox': checkbox,
        'label': label,
        'help_text': help_text,
    }


@register.inclusion_tag('dg_board/_form_errors.html')
def form_errors(form, fields: bool = False) -> dict:
    """The errors of a form or formset that belong to none of its fields; with `fields`, every field's
    errors too, for a form whose fields are laid out without them."""
    if isinstance(form, BaseFormSet):
        return {'errors': form.non_form_errors()}
    errors = list(form.non_field_errors())
    if fields:
        errors += [error for name in form.fields for error in form.errors.get(name, [])]
    return {'errors': errors}
