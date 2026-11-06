"""Every installed Gilde app, and the MCP endpoint, under one include:

    path('gilde/', include('gilde.urls'))

Core's pages and endpoints come first (`gilde/mcp`), then each app at the prefix its AppConfig names in
`gilde_url_prefix` (`gilde/board/`). Each keeps its own namespace, such as `gilde_board`.
"""

from django.apps import apps
from django.urls import include, path

urlpatterns = [
    path('', include('gilde.core.urls')),
    *(
        path(f'{config.gilde_url_prefix}/', include(f'{config.name}.urls'))
        for config in apps.get_app_configs()
        if getattr(config, 'gilde_url_prefix', None)
    ),
]
