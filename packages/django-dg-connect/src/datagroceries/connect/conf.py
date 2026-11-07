"""django-oauth-toolkit's settings for signing in agents: the authorization-code flow with PKCE only,
for public clients that name themselves by a Client ID Metadata Document on an allowed host, as every
Claude client and VS Code do, with rotated refresh tokens and only a hash of each token stored (RFC 9700).
After Eddy Grid's connector, which runs on these in production.

A project that sets `OAUTH2_PROVIDER` itself keeps what it sets; these fill in the rest.
"""

from django.conf import settings
from oauth2_provider.settings import oauth2_settings

DEFAULTS = {
    'SCOPES_BACKEND_CLASS': 'datagroceries.connect.oauth.AreaScopes',
    'PKCE_REQUIRED': True,
    'OAUTH2_GRANT_TYPES_SUPPORTED': ['authorization_code', 'refresh_token'],
    'OAUTH2_RESPONSE_TYPES_SUPPORTED': ['code'],
    # Public clients only: PKCE instead of a secret.
    'OAUTH2_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED': ['none'],
    # Claude Code signs in through a browser that sends it back to a port of its own on localhost.
    'ALLOWED_REDIRECT_URI_SCHEMES': ['https', 'http'],
    'ALLOW_LOCALHOST_LOOPBACK': True,
    # Client ID Metadata Documents: a client names itself by a URL whose document the toolkit fetches,
    # so the Claude apps and VS Code connect with the MCP endpoint's address alone. Only from these
    # hosts, those of well-known clients: anyone else could otherwise register by URL, and ask people to
    # let a lookalike act as them. No dynamic client registration. Other clients use a personal token.
    'CIMD_ENABLED': True,
    'CIMD_METADATA_FETCHER': 'datagroceries.connect.oauth.OfferedGrantsMetadataFetcher',
    'CIMD_REGISTRATION_PERMISSION_CLASSES': ('oauth2_provider.cimd.HostAllowlistCIMDPermission',),
    'CIMD_ALLOWED_HOSTS': ['claude.ai', '.claude.ai', '.claude.com', '.anthropic.com', 'vscode.dev'],
    'COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT': True,
    'COMPLIANT_BCP_RFC9700_PASSWORD_GRANT': True,
    'COMPLIANT_BCP_RFC9700_PKCE_METHOD': True,
    'COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT': True,
    'COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS': True,
    'COMPLIANT_BCP_RFC9700_TOKEN_STORAGE': True,
    # A refresh token works once. Replaying a used one revokes all of that connection's tokens, as it
    # suggests a stolen token. No grace period for a client retrying a refresh it lost: that would have to
    # hand back the old token, of which only a hash is stored. Such a client signs in again.
    'REFRESH_TOKEN_REUSE_PROTECTION': True,
    'REFRESH_TOKEN_GRACE_PERIOD_SECONDS': 0,
    # Once allowed, connecting the same app again skips the question.
    'REQUEST_APPROVAL_PROMPT': 'auto',
    'ACCESS_TOKEN_EXPIRE_SECONDS': 60 * 60,
    # Counted from when the last access token expired: a connection unused for three months stops, as a
    # personal token does, and one in use never does.
    'REFRESH_TOKEN_EXPIRE_SECONDS': 90 * 24 * 60 * 60,
}

settings.OAUTH2_PROVIDER = {**DEFAULTS, **getattr(settings, 'OAUTH2_PROVIDER', {})}
# The toolkit may have read its settings already, when it was installed before this app.
oauth2_settings.reload()
