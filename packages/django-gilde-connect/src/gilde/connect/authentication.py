"""The two ways in that this package registers with core (gilde.core.authentication): personal tokens,
and the Claude connector's OAuth tokens. Both come as `Authorization: Bearer …`; a personal token's key
starts with `gilde_`, so each knows its own, and a token of the host project's own passes both by."""

from django.utils import timezone
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from gilde.connect.models import ApiToken


class ApiTokenAuthentication(TokenAuthentication):
    """A personal token: `Bearer gilde_…`, as MCP clients send it, or `Token gilde_…`, as DRF does."""

    keyword = 'Bearer'

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        key = header[1] if len(header) == len(('Bearer', 'key')) else None
        if key is not None and not key.startswith(ApiToken.PREFIX.encode()):
            return None  # another way in's token
        # DRF reads one keyword per class; a request sent DRF's way gets DRF's.
        if header and header[0].lower() == b'token':
            self.keyword = 'Token'
        return super().authenticate(request)

    def authenticate_credentials(self, key):
        token = ApiToken.objects.select_related('user').filter(key_hash=ApiToken.hash(key)).first()
        if token is None or not token.is_usable:
            raise AuthenticationFailed('Invalid, expired or revoked token.')
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token.user, token


class ConnectorAuthentication(OAuth2Authentication):
    """An OAuth token of the Claude connector, or of another MCP client that signed in the same way. A
    deactivated user's tokens stop at once, as their personal tokens do."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None and not result[0].is_active:
            raise AuthenticationFailed('This account is deactivated.')
        return result
