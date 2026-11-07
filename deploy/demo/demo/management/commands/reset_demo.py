import shutil

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from demo import seed


class Command(BaseCommand):
    help = 'Start the demo again: empty the database and the uploads, and fill it with the same board and wiki.'

    def handle(self, *args, **options):
        # Migrations first, so a fresh server needs no separate migrate. Flush empties every table, the
        # wiki's pages and their history, the visitors, their sign-ins and Claude's connections too, and adds
        # the permissions back.
        call_command('migrate', interactive=False, verbosity=0)
        call_command('flush', interactive=False, verbosity=0)
        # What is in the uploads folder, not the folder, which the service's sandbox names.
        for upload in settings.MEDIA_ROOT.glob('*'):
            if upload.is_dir():
                shutil.rmtree(upload)
            else:
                upload.unlink()
        seed.seed()
        self.stdout.write('The demo starts again.')
