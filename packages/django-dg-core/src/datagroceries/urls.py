"""Every installed DataGroceries app, and the MCP endpoint, under one include:

    path('dg/', include('datagroceries.urls'))

Core's pages and endpoints come first (`dg/mcp`), then each app at the prefix its AppConfig names in
`dg_url_prefix` (`dg/board/`). Each keeps its own namespace, such as `dg_board`.
"""

from django.apps import apps
from django.urls import include, path

urlpatterns = [
    path('', include('datagroceries.core.urls')),
    *(
        path(f'{config.dg_url_prefix}/', include(f'{config.name}.urls'))
        for config in apps.get_app_configs()
        if getattr(config, 'dg_url_prefix', None)
    ),
]
