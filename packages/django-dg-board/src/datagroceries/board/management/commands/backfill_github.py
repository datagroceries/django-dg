import datetime

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from datagroceries.board import github


class Command(BaseCommand):
    help = (
        "Link the repository's history to the tickets it mentions: the commits on its default branch, and "
        'every pull request. Branches are left to the webhook, as GitHub keeps no record of who made one '
        'when. Safe to run again: a link that exists is brought up to date.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--since',
            type=datetime.date.fromisoformat,
            help='Only commits and pull requests from this date, e.g. 2025-03-01.',
        )

    def handle(self, *args, **options):
        if not settings.DG_BOARD_GITHUB_TOKEN:
            raise CommandError('DG_BOARD_GITHUB_TOKEN is not set: see "GitHub" in the django-dg-board README.')
        try:
            self._backfill(options['since'])
        except requests.HTTPError as error:
            if error.response.status_code in (401, 403, 404):
                raise CommandError(
                    f'GitHub refused {error.response.url} ({error.response.status_code}): '
                    'DG_BOARD_GITHUB_TOKEN needs read-only Contents, Pull requests and Metadata on the repository.',
                ) from error
            raise

    def _backfill(self, since):
        seen = created = 0
        for page in github.default_branch_commits(since=since):
            seen += len(page)
            created += github.record_commits(page)
            self.stdout.write(f'  {seen} commits read, {created} links made')
        commits, seen = created, 0
        for page in github.pull_requests(since=since):
            seen += len(page)
            created += sum(github.record_pull_request(pull_request) for pull_request in page)
            self.stdout.write(f'  {seen} pull requests read, {created - commits} links made')
        self.stdout.write(f'Done: {commits} new links to commits, {created - commits} to pull requests.')
