"""Who takes part in the DataGroceries apps, and how each person shows.

Who may use an app is a Django permission of that app's, such as "Can use the board"
(`dg_board.use`), granted to groups or people in the admin; superusers have every one. Those who may
use an app are its people: they can be assigned and @-mentioned there.

Within an app, what someone may do comes from the same class: `may(user, right, group)`, with one of
`RIGHTS` in one of the board's groups. By default whoever may use the app may do everything there; a
project that wants less for some people says so in `may`.

How the apps see a person comes from one class, `People`. A host project changes what differs in a
subclass and names it in `DG_PEOPLE`, as allauth's adapters do: who may use an app, what they may do
there, someone's name, their @-handle, their email address, their image, the language to write to them
in. The defaults assume
nothing about the user model beyond what Django's own `AbstractBaseUser` has: a username, and an email
field only when the model names one.
"""

import functools
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.core.signals import setting_changed
from django.db.models import QuerySet
from django.dispatch import receiver
from django.utils.module_loading import import_string
from django.utils.translation import get_supported_language_variant

from datagroceries.core import history

HANDLE_RE = re.compile(r'[a-z0-9](?:[a-z0-9._-]*[a-z0-9_-])?')
# What someone may do in a part of an app, each including the ones before it: see it (and search and
# watch), also comment, also create and change what is in it, also change the part itself.
RIGHTS = ('read', 'comment', 'write', 'manage')


def includes(granted: str, right: str) -> bool:
    """Whether `granted`, one of RIGHTS, includes `right`: "write" includes "comment", not "manage"."""
    return RIGHTS.index(granted) >= RIGHTS.index(right)


def _has_field(model_or_user, name: str) -> bool:
    try:
        model_or_user._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


class People:
    """The default way the DataGroceries apps see people. Subclass it to change what differs, and name the
    subclass in `DG_PEOPLE`."""

    def may_use(self, user, area) -> bool:
        """Whether `user` may use `area` now: by default, an active user with its permission."""
        return user.is_authenticated and user.is_active and user.has_perm(area.permission)

    def may(self, user, right: str, group) -> bool:
        """Whether `user`, who may use the app (`may_use`), has `right`, one of RIGHTS, in `group`: a
        board group, or None for what belongs to no group, such as making a new one. Each right includes
        the ones before it, so a subclass answers "comment" with yes for whoever may "write" (`includes`
        helps). By default yes: whoever may use the app may do everything in it.

        For less, look anywhere: `user.has_perm`, django-guardian, a model of the project's own. Who may not
        read a group does not see its tickets, nor hear about them."""
        return True

    def members(self, area) -> QuerySet:
        """Everyone who may use `area`, by name: by default the active users with its permission, through
        a group or of their own, and the superusers. A subclass that changes `may_use` changes this too,
        though it lists people faster by changing this as well."""
        manager = get_user_model()._default_manager
        # Django's ModelBackend, or a subclass of it such as allauth's, can list who has a permission.
        backends = [path for path in settings.AUTHENTICATION_BACKENDS if hasattr(import_string(path), 'with_perm')]
        if backends and type(self).may_use is People.may_use:
            users = manager.with_perm(area.permission, is_active=True, backend=backends[0])
        else:
            users = manager.filter(pk__in=[user.pk for user in manager.all() if self.may_use(user, area)])
        return users.order_by(*self.ordering())

    def ordering(self) -> tuple:
        """How `members` sorts: by the name fields the user model has, else the username."""
        model = get_user_model()
        for fields in (('first_name', 'last_name'), ('name',)):
            if all(_has_field(model, field) for field in fields):
                return (*fields, model.USERNAME_FIELD)
        return (model.USERNAME_FIELD,)

    def name(self, user) -> str:
        """The person's name as the apps show it: their full name when the user model has one, else
        their username."""
        if _has_field(user, 'first_name') and _has_field(user, 'last_name'):
            full = f'{user.first_name} {user.last_name}'.strip()
        elif _has_field(user, 'name'):
            full = (user.name or '').strip()
        else:
            full = ''
        return full or user.get_username()

    def short_name(self, user) -> str:
        """What a small card has room for: the first name when there is one, else the first word of
        the name."""
        if _has_field(user, 'first_name') and user.first_name:
            return user.first_name
        return self.name(user).split()[0]

    def handle(self, user) -> str | None:
        """What follows the @ that mentions this person, or None if nothing does. It holds letters,
        digits, ".", "_" and "-", and no two people may share one. By default the username, lowercased,
        with "-" for what a handle cannot hold: "anna@example.com" becomes "anna-example.com"."""
        return re.sub(r'[^a-z0-9._-]+', '-', user.get_username().lower()).strip('.-') or None

    def email(self, user) -> str | None:
        """Where the person's notifications go, or None for someone without an address."""
        return getattr(user, user.get_email_field_name(), None) or None

    def avatar_url(self, user, size: int) -> str | None:
        """The URL of the person's image at least `size` pixels square, or None to show their initials."""
        return None

    def language(self, user) -> str | None:
        """The language to write to the person in, such as "nl", or None for the project's (LANGUAGE_CODE).
        By default a `language` field on the user model, when it has one; Django itself keeps none."""
        return (user.language or None) if _has_field(user, 'language') else None


@functools.cache
def _people() -> People:  # cleared when the setting changes, as in tests
    path = getattr(settings, 'DG_PEOPLE', None)
    return import_string(path)() if path else People()


@receiver(setting_changed)
def _forget_people(setting, **kwargs):
    if setting == 'DG_PEOPLE':
        _people.cache_clear()


def _area(scope: str):
    from datagroceries.core import areas  # noqa: PLC0415 - areas imports this module

    return areas.AREAS[scope]


def may_use(user, scope: str) -> bool:
    return _people().may_use(user, _area(scope))


def may(user, right: str, group) -> bool:
    if right not in RIGHTS:
        raise ValueError(f'Unknown right {right!r}; one of {", ".join(RIGHTS)}.')
    return _people().may(user, right, group)


def members(scope: str) -> QuerySet:
    return _people().members(_area(scope))


def name(user) -> str:
    return _people().name(user)


def short_name(user) -> str:
    return _people().short_name(user)


def handle(user) -> str | None:
    found = _people().handle(user)
    return found.lower() if found and HANDLE_RE.fullmatch(found.lower()) else None


def email(user) -> str | None:
    return _people().email(user)


def avatar_url(user, size: int) -> str | None:
    return _people().avatar_url(user, size)


def language(user) -> str:
    """The language to write to the person in: theirs, when the project has it in LANGUAGES, else the
    project's."""
    try:
        return get_supported_language_variant(_people().language(user) or settings.LANGUAGE_CODE)
    except LookupError:
        return settings.LANGUAGE_CODE


def by_handle(scope: str) -> dict:
    """Everyone who may use the area and can be @-mentioned, by their handle."""
    return {found: user for user in members(scope) if (found := handle(user))}


def mentioned(scope: str, handles: set[str]) -> list:
    """The people of the area these @-handles name; handles that name nobody are left out."""
    return [user for found, user in by_handle(scope).items() if found in handles]


def may_use_required(scope: str):
    """Lets people who may use the area into a page; sends anyone not signed in to sign in, and refuses
    everyone else."""

    def check(user) -> bool:
        if user.is_authenticated and not may_use(user, scope):
            raise PermissionDenied
        return user.is_authenticated

    def decorator(view):
        @functools.wraps(view)
        def recorded(request, *args, **kwargs):
            with history.recording(request):
                return view(request, *args, **kwargs)

        return user_passes_test(check)(recorded)

    return decorator
