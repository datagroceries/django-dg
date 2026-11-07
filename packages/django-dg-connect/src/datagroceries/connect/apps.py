from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConnectConfig(AppConfig):
    name = 'datagroceries.connect'
    label = 'dg_connect'
    verbose_name = _('Connected agents')
    default_auto_field = 'django.db.models.BigAutoField'
    # Where datagroceries.urls mounts the "Connect an agent" page and the OAuth endpoints.
    dg_url_prefix = 'connect'

    def ready(self):
        from datagroceries.connect import checks, oauth  # noqa: F401 - registers the system checks
        from datagroceries.connect.authentication import ApiTokenAuthentication, ConnectorAuthentication
        from datagroceries.core import authentication

        authentication.register(ApiTokenAuthentication)
        authentication.register(ConnectorAuthentication, authorization_server=oauth.issuer)
