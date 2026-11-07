from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'gilde.core'
    label = 'gilde_core'
    verbose_name = 'Gilde'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from gilde.core import (
            checks,  # noqa: F401 - registers the system checks
            markdown,
        )
        from gilde.core.mentions import Mentions

        markdown.register(Mentions)
