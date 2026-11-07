"""How a program gets into the Gilde apps' API and MCP endpoint. Core checks credentials and never issues
them (docs/decisions.md); every way in lands on the same check, `opens`.

The ways in, in order:

1. Those of Gilde packages that issue tokens, such as django-gilde-connect's OAuth for the Claude
   connector and its personal tokens: they `register` here, as apps register their areas.
2. The host project's own, the DRF authentication classes listed in `GILDE_AUTHENTICATION_CLASSES`:
   its own tokens, JWT, anything DRF can check.

Whatever let a request in, it reaches an area only while its user may use it, and only if the token,
when it carries scopes, covers it. A request let in without credentials gets a 401 that points at the
protected resource metadata (RFC 9728), which names the authorization server, so an MCP client given
only the endpoint's address finds where to sign in.
"""

from collections.abc import Callable

from django.conf import settings
from django.dispatch import receiver
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils import translation
from django.utils.module_loading import import_string
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from simple_history.models import HistoricalRecords
from simple_history.signals import pre_create_historical_record

from gilde.core import areas, history

# What Gilde packages that issue tokens registered (`register`).
_ways_in: list[type] = []
_authorization_servers: list[Callable] = []


def register(authentication_class: type, authorization_server: Callable | None = None):
    """For a Gilde package that issues tokens: its DRF authentication class, and a function that takes the
    request and returns the URL of its authorization server, if it has one."""
    _ways_in.append(authentication_class)
    if authorization_server:
        _authorization_servers.append(authorization_server)


def authorization_server(request) -> str | None:
    """Where an MCP client signs in: the project's own authorization server, `GILDE_AUTHORIZATION_SERVER`,
    or a registered one."""
    if url := getattr(settings, 'GILDE_AUTHORIZATION_SERVER', None):
        return url
    return _authorization_servers[0](request) if _authorization_servers else None


class NoWayIn(BaseAuthentication):
    """Lets nobody in. Always last, so that without any other way in a request still gets a 401 that says
    where to sign in, not DRF's 403."""

    def authenticate(self, request):
        return None


class GildeAuthentication:
    """For an APIView: every way in, and a 401 that says where to sign in."""

    def get_authenticators(self):
        extra = getattr(settings, 'GILDE_AUTHENTICATION_CLASSES', ())
        return [*(cls() for cls in _ways_in), *(import_string(path)() for path in extra), NoWayIn()]

    def dispatch(self, request, *args, **kwargs):
        # In English whatever the project's language: the API and the tools are for programs and agents,
        # and its error messages come from the same forms and models as the pages'.
        with history.recording(request), translation.override('en'):
            return super().dispatch(request, *args, **kwargs)

    def get_authenticate_header(self, request):
        if authorization_server(request):
            return f'Bearer resource_metadata="{request.build_absolute_uri(reverse("gilde_core:resource_metadata"))}"'
        return 'Bearer'


def opens(request, scope: str) -> bool:
    """Whether the request reaches the area `scope`: its user may use it, and the token, if it carries a
    `scope` (space-separated area names, as OAuth tokens and Gilde's personal tokens have), covers it."""
    if not request.user.is_authenticated or scope not in areas.scopes_for(request.user):
        return False
    # A page's request, signed in with a session, has no `auth`, and so no token to narrow it.
    granted = getattr(getattr(request, 'auth', None), 'scope', None)
    return not isinstance(granted, str) or scope in granted.split()


class HasTokenScope(BasePermission):
    """Lets in requests that reach the view's area, `token_scope` (opens)."""

    message = 'This token does not open this part of the API, or you no longer have access to it.'

    def has_permission(self, request, view):  # type: ignore[override]
        return opens(request, view.token_scope)


def resource_metadata(request):
    """The protected resource metadata of the MCP endpoint (RFC 9728): what it is, and where to sign in
    for it. There is none while nothing issues tokens for the Claude connector."""
    server = authorization_server(request)
    if not server:
        raise Http404('No authorization server.')
    return JsonResponse(
        {
            'resource': request.build_absolute_uri(reverse('gilde_core:mcp')),
            'authorization_servers': [server],
            'scopes_supported': list(areas.AREAS),
            'bearer_methods_supported': ['header'],
            'resource_name': 'Gilde',
        }
    )


@receiver(pre_create_historical_record)
def mark_token_changes(sender, history_instance, **kwargs):
    """Changes made with a token say so in their history: "via Claude Code on my laptop" for a token with a
    name, "via Claude" for an OAuth token, after its app, or "via API" for a token of the project's own.

    DRF sets the token on the Django request, which gilde.core.history keeps for the request.
    """
    request = getattr(HistoricalRecords.context, 'request', None)
    token = getattr(request, 'auth', None)
    if token is not None and not history_instance.history_change_reason:
        application = getattr(token, 'application', None)
        name = getattr(token, 'name', None) or getattr(application, 'name', None) or 'API'
        history_instance.history_change_reason = f'via {name}'
