import dataclasses
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


def grant(user, *permissions: str):
    """Gives `user` these permissions, each as "app_label.codename"."""
    for permission in permissions:
        app_label, codename = permission.split('.')
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    return user


def person(*permissions: str, **fields):
    """A user with these permissions."""
    return grant(get_user_model().objects.create_user(**fields), *permissions)


def addressed(pks) -> list[str]:
    """Who a notification went to, by email address: the people whose keys the task was given."""
    return sorted(get_user_model().objects.filter(pk__in=pks).values_list('email', flat=True))


@dataclasses.dataclass
class IssuedToken:
    """A token as the tests hand it out, shaped as the real ones are: a name, and the space-separated areas
    it opens."""

    user_id: int
    name: str
    scope: str


TOKENS: dict[str, IssuedToken] = {}
# For override_settings(DG_AUTHENTICATION_CLASSES=...), so the apps' tests need no token package.
TEST_AUTHENTICATION = ['datagroceries.core.tests.IssuedTokenAuthentication']


def issue(user, name: str = 'Claude Code', scopes=('board',)) -> str:
    """A key for `user`, opening `scopes`, as `Authorization: Bearer <key>`."""
    key = f'test-{secrets.token_hex(8)}'
    TOKENS[key] = IssuedToken(user.pk, name, ' '.join(scopes))
    return key


class IssuedTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = TOKENS.get(request.META.get('HTTP_AUTHORIZATION', '').removeprefix('Bearer '))
        if token is None:
            return None
        user = get_user_model().objects.get(pk=token.user_id)
        if not user.is_active:
            raise AuthenticationFailed('This account is deactivated.')
        return user, token

    def authenticate_header(self, request):
        return 'Bearer'
