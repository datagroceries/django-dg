# django-dg-connect

Connect Claude and other AI agents to the DataGroceries apps, as the person who connects them. Optional: a
project that has its own API logins or OAuth server can leave it out and name those instead. See
[docs/integrating.md](https://github.com/datagroceries/django-dg/blob/main/docs/integrating.md).

- **The Claude connector.** claude.ai, Claude Desktop, mobile and Claude Code, and VS Code too, connect
  with the address of the MCP endpoint alone, then sign in through the project's own login and allow the
  apps. An OAuth authorization server on [django-oauth-toolkit](https://django-oauth-toolkit.readthedocs.io/),
  set up as the Claude clients need it (`conf.py`): PKCE only, Client ID Metadata Documents from Claude's
  hosts and vscode.dev, no dynamic registration, rotated refresh tokens, only hashes stored.
- **Personal tokens**, for scripts, CI and agents that cannot sign in that way: named, limited to the apps
  ticked, `dg_`-prefixed, shown once, stored as a hash.
- **One page, "Connect an agent"** (`dg/connect/`): how to connect Claude and Claude Code, every
  connected app and every token, each revocable.

## Installing

```bash
pip install django-dg-connect
```

```python
INSTALLED_APPS = [..., 'oauth2_provider', 'datagroceries.core', 'datagroceries.connect', ...]
```

Then `manage.py migrate`. The URLs come with `path('dg/', include('datagroceries.urls'))`. A project that sets
`OAUTH2_PROVIDER` itself keeps what it sets, and the rest is filled in.

The Claude apps reach the site from Anthropic's servers, so only over HTTPS on the internet; Claude Code
connects from the person's own computer and works on an internal network too.

## How it works

- Both ways in register with core (`datagroceries.core.authentication`), which checks every request the same way:
  the person may still use the app, and the token's scope covers it. Losing access to an app ends it on
  every connection and token at once, and so does deactivating the person.
- The OAuth scopes are the DataGroceries apps' areas. A connection gets all of them; which it opens is decided on
  every call.
- The MCP endpoint's `401` points at its protected resource metadata (RFC 9728, in core), which names this
  authorization server. Its own metadata is at `dg/connect/.well-known/oauth-authorization-server`, and
  also at `dg/connect/.well-known/openid-configuration`, where MCP clients look for an issuer with a
  path.
- claude.ai's client document also lists the jwt-bearer grant, which the toolkit refuses beside the
  authorization code; `OfferedGrantsMetadataFetcher` drops the grants not offered.
- A connection or a token unused for three months stops.

## What Claude needs from a connector

From [Anthropic's documentation](https://claude.com/docs/connectors/building/authentication), and what
connect does for each:

- The same OAuth support serves claude.ai, Desktop, mobile, Cowork and Claude Code.
- An unauthenticated request gets a `401` whose `WWW-Authenticate: Bearer resource_metadata="…"` points at
  the protected resource metadata, whose `resource` equals the MCP URL exactly. Claude uses only the
  first authorization server it lists. (Core does this.)
- Client registration by Client ID Metadata Document, used when the server advertises
  `client_id_metadata_document_supported` and `none` as a token endpoint auth method, or else dynamic
  client registration. (CIMD only, from Claude's hosts and vscode.dev.)
- PKCE S256, form-encoded token requests, rotated refresh tokens, `invalid_grant` for a dead refresh token,
  answers within 10 seconds.
- Callbacks: `https://claude.ai/api/mcp/auth_callback` for the Claude apps, and any-port loopback on both
  `localhost` and `127.0.0.1` for Claude Code.
- For the Claude apps the server must be reachable from Anthropic's network (`160.79.104.0/21`) over HTTPS.

Further reading: the [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization),
Anthropic's [custom connectors via remote MCP servers](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers),
and django-oauth-toolkit's [changelog](https://django-oauth-toolkit.readthedocs.io/en/latest/changelog.html).
