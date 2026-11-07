from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'datagroceries.core'
    label = 'dg_core'
    verbose_name = 'DataGroceries'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from datagroceries.core import (
            checks,  # noqa: F401 - registers the system checks
            markdown,
        )
        from datagroceries.core.mentions import Mentions

        markdown.register(Mentions)
