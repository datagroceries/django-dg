"""OAuth for the Claude connector: claude.ai, Claude Desktop, mobile and Claude Code sign in as the person
who connects them, with the MCP endpoint's address alone.

django-oauth-toolkit is the authorization server (its settings are in conf.py); this module holds what
is DataGroceries' in it, after Eddy Grid's connector. Its pages sit behind the host project's own login,
whatever that is. The OAuth scopes are the DataGroceries areas, and a token opens an area only while its person
may use it (datagroceries.core.authentication.opens), checked on every call.

The endpoints live under the include's prefix (`dg/connect/`), and so does the issuer. For an issuer
with a path, the MCP specification has a client look for its metadata at
`/.well-known/oauth-authorization-server/dg/connect`, at `/.well-known/openid-configuration/dg/connect`,
and at `dg/connect/.well-known/openid-configuration`; the last is the one under the prefix, so it is
served here as well as the toolkit's own `dg/connect/.well-known/oauth-authorization-server`.
"""

from urllib.parse import urlparse

from django.shortcuts import render
from django.urls import path, reverse
from oauth2_provider import views
from oauth2_provider.cimd import HostAllowlistCIMDPermission, SafeMetadataFetcher
from oauth2_provider.scopes import BaseScopes
from oauth2_provider.settings import oauth2_settings

from datagroceries.core import areas


def issuer(request) -> str:
    """The authorization server's address, as its metadata gives it: core names it to MCP clients."""
    return oauth2_settings.oauth2_authorization_server_issuer(request)


class OfferedGrantsMetadataFetcher(SafeMetadataFetcher):
    """The toolkit's fetcher of Client ID Metadata Documents, keeping only the grant types we offer.

    claude.ai's document also lists the jwt-bearer grant, for enterprise SSO, and the toolkit refuses a
    document with more than one grant besides refresh_token. RFC 7591 lets a server drop the grant types
    it does not support.
    """

    def fetch(self, client_id):
        metadata, max_age = super().fetch(client_id)
        if isinstance(metadata.get('grant_types'), list):
            offered = oauth2_settings.OAUTH2_GRANT_TYPES_SUPPORTED
            metadata = {**metadata, 'grant_types': [grant for grant in metadata['grant_types'] if grant in offered]}
        return metadata, max_age


class AreaScopes(BaseScopes):
    """The scopes are the DataGroceries areas. A connection is given all of them: which it opens is decided on
    every call by its person's access, so a change in that counts at once."""

    def get_all_scopes(self):
        return {scope: area.label for scope, area in areas.AREAS.items()}

    def get_available_scopes(self, application=None, request=None, *args, **kwargs):
        return list(areas.AREAS)

    def get_default_scopes(self, application=None, request=None, *args, **kwargs):
        return list(areas.AREAS)


class AuthorizationView(views.AuthorizationView):
    """Where someone lets Claude act as them: the toolkit's page, in DataGroceries' layout, listing the apps they
    may use. Someone who may use none is told so, and whom to ask, rather than getting a 404 that reads
    as a broken link."""

    template_name = 'dg_connect/authorize.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not areas.scopes_for(request.user):
            return render(request, 'dg_connect/no_access.html', status=403)
        return super().dispatch(request, *args, **kwargs)

    def error_response(self, error, application, **kwargs):
        """A client that names itself by a URL on a host not allowed here is told so, and what to use
        instead, rather than the toolkit's "Invalid client_id parameter value"."""
        client_id = self.request.GET.get('client_id', '')
        if client_id.startswith('https://') and not HostAllowlistCIMDPermission().has_permission(
            self.request, client_id
        ):
            kwargs['refused_host'] = urlparse(client_id).hostname
        return super().error_response(error, application, **kwargs)

    def get_context_data(self, **kwargs):
        requested = kwargs.get('scopes') or list(areas.AREAS)
        return {
            **super().get_context_data(**kwargs),
            'areas': [areas.AREAS[scope].label for scope in areas.scopes_for(self.request.user) if scope in requested],
            # The MCP specification wants the redirect's host on the page: with CIMD the app names
            # itself, and where the person is sent back to says whom they let in.
            'redirect_host': urlparse(kwargs['redirect_uri']).hostname if kwargs.get('redirect_uri') else None,
        }


class OpenIDConfigurationView(views.OAuthServerMetadataView):
    """The authorization server's metadata at the address under the prefix that MCP clients try. The
    toolkit derives the issuer from the request's path, so it is given the usual one."""

    def get(self, request, *args, **kwargs):
        request.path = reverse('oauth2_provider:oauth-server-metadata')
        return super().get(request, *args, **kwargs)


# Included by datagroceries.connect.urls under its prefix. The toolkit reverses its own views by this namespace.
app_name = 'oauth2_provider'
urlpatterns = [
    path(
        '.well-known/oauth-authorization-server', views.OAuthServerMetadataView.as_view(), name='oauth-server-metadata'
    ),
    path('.well-known/openid-configuration', OpenIDConfigurationView.as_view()),
    path('oauth/authorize/', AuthorizationView.as_view(), name='authorize'),
    path('oauth/token/', views.TokenView.as_view(), name='token'),
    path('oauth/revoke_token/', views.RevokeTokenView.as_view(), name='revoke-token'),
]
