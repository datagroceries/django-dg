# Changelog of django-gilde-core

## 1.0.0 (unreleased)

The first release: the one MCP endpoint for every installed Gilde app, the checks on every way in
(registered token packages and the project's own DRF authentication, with the `401` that points MCP
clients at their authorization server), people as a Django permission per app and one `People` class,
notifications by email and Slack with fallback, Gilde's own layout with its assets, one URL include,
and system checks. Django 5.2 LTS and 6.x, Python 3.11 and newer.
