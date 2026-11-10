"""Making an account on hq, to comment on the wiki's public folders (people.py): an email address and a
name, confirmed with a code mailed to it. Every new account is a reader."""

from allauth.account.adapter import DefaultAccountAdapter
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.utils.text import capfirst

# The user group of everyone who made an account here: they may use the wiki, not the board.
READERS = 'Readers'


def readers() -> Group:
    group, made = Group.objects.get_or_create(name=READERS)
    if made:
        group.permissions.add(Permission.objects.get(content_type__app_label='dg_wiki', codename='use'))
    return group


class AccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit)
        if commit:
            user.groups.add(readers())
        return user


def _label(name: str) -> str:
    """Django's own name for the field, so it is translated already."""
    return capfirst(get_user_model()._meta.get_field(name).verbose_name)


class SignupForm(forms.Form):
    """The name that shows on a comment; allauth's adapter saves it."""

    first_name = forms.CharField(label=_label('first_name'), max_length=150)
    last_name = forms.CharField(label=_label('last_name'), max_length=150, required=False)

    def signup(self, request, user):
        pass
