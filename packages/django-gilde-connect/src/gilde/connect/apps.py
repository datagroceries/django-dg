from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConnectConfig(AppConfig):
    name = 'gilde.connect'
    label = 'gilde_connect'
    verbose_name = _('Connected agents')
    default_auto_field = 'django.db.models.BigAutoField'
    # Where gilde.urls mounts the "Connect an agent" page and the OAuth endpoints.
    gilde_url_prefix = 'connect'

    def ready(self):
        from gilde.connect import checks, oauth  # noqa: F401 - registers the system checks
        from gilde.connect.authentication import ApiTokenAuthentication, ConnectorAuthentication
        from gilde.core import authentication

        authentication.register(ApiTokenAuthentication)
        authentication.register(ConnectorAuthentication, authorization_server=oauth.issuer)
