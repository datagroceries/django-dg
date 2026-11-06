from django.urls import path
from django.views.i18n import JavaScriptCatalog, set_language

from gilde.core import authentication
from gilde.core.mcp import McpView

app_name = 'gilde_core'

urlpatterns = [
    # With or without the slash: some MCP clients drop it, and a redirect would lose the POST.
    path('mcp', McpView.as_view(), name='mcp'),
    path('mcp/', McpView.as_view()),
    # Where the MCP endpoint's 401 points (RFC 9728).
    path('.well-known/oauth-protected-resource', authentication.resource_metadata, name='resource_metadata'),
    # The texts the apps' JavaScript shows, in the active language: gettext() and interpolate() there.
    path(
        'jsi18n/',
        JavaScriptCatalog.as_view(packages=['gilde.core', 'gilde.connect', 'gilde.board']),
        name='javascript_catalog',
    ),
    # The language switch in the header (gilde_core/base.html): Django's own view, which remembers the choice
    # in a cookie that LocaleMiddleware reads.
    path('language/', set_language, name='set_language'),
]
