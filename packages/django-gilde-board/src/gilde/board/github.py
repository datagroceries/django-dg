"""Links code to the tickets whose keys it mentions, as CodeReferences: commits on the repository's
default branch, branches, and pull requests.

- A commit counts by the keys in its message ("T-123 Fix the invoice"); on the default branch that is
  the squashed pull request.
- A branch counts by the keys in its name, in any case ("anna/t-123-invoices"). It stands in for its
  work until a pull request is opened from it, which then replaces it on the ticket.
- A pull request counts by the keys in its title and its branch's name, not its description, which
  names other tickets in passing. Its state follows it (open, merged, closed), and a key taken out of
  its title takes its link away.

The webhook (views.github_webhook) calls handle_event for each delivery; the backfill_github command reads the
history once. The repository is GILDE_BOARD_GITHUB_REPOSITORY.
"""

import datetime
import re
from collections.abc import Iterable, Iterator

import requests
from django.conf import settings
from django.utils import timezone

from gilde.board.models import CodeReference
from gilde.board.ticket_links import CANDIDATE_RE, resolve_keys

API_URL = 'https://api.github.com'
PAGE_SIZE = 100
# Keys in a branch name are often lower case: anna/t-123-invoices.
ANY_CASE_KEY_RE = re.compile(r'\b[A-Za-z][A-Za-z0-9]*-\d+\b')
# Pull request events that can change what it links to, or its state.
PULL_REQUEST_ACTIONS = {'opened', 'edited', 'reopened', 'closed', 'synchronize'}


def _keys(text: str, *, any_case: bool = False) -> set[str]:
    if any_case:
        return {key.upper() for key in ANY_CASE_KEY_RE.findall(text)}
    return set(CANDIDATE_RE.findall(text))


def _link(kind: str, ref: str, keys: set[str], fields: dict) -> int:
    """Link `ref` to the tickets `keys` name, and only those; how many links are new."""
    tickets = set(resolve_keys(keys).values()) if keys else set()
    CodeReference.objects.filter(kind=kind, ref=ref).exclude(ticket__in=tickets).delete()
    created = 0
    for ticket in tickets:
        _reference, new = CodeReference.objects.update_or_create(ticket=ticket, kind=kind, ref=ref, defaults=fields)
        created += new
    return created


def record_commits(commits: Iterable[dict]) -> int:
    """Link each commit to the tickets its message names; how many links are new.

    A commit is a dict with sha, message, url, author (a name) and committed_at.
    """
    created = 0
    for commit in commits:
        keys = _keys(commit['message'])
        if keys:
            created += _link(
                CodeReference.Kind.COMMIT,
                commit['sha'],
                keys,
                {
                    'url': commit['url'],
                    'title': commit['message'].splitlines()[0][:300],
                    'author': commit['author'][:200],
                    'happened_at': commit['committed_at'],
                },
            )
    return created


def record_pull_request(pull_request: dict) -> int:
    """Link a pull request, as GitHub describes one, to the tickets its title and branch name."""
    branch = pull_request['head']['ref']
    created = _link(
        CodeReference.Kind.PULL_REQUEST,
        str(pull_request['number']),
        _keys(pull_request['title']) | _keys(branch, any_case=True),
        {
            'url': pull_request['html_url'],
            'title': pull_request['title'][:300],
            'author': pull_request['user']['login'][:200],
            'state': 'merged' if pull_request.get('merged_at') else pull_request['state'],
            'happened_at': datetime.datetime.fromisoformat(pull_request['created_at']),
        },
    )
    # From now on the pull request stands for its branch.
    CodeReference.objects.filter(kind=CodeReference.Kind.BRANCH, ref=branch).delete()
    return created


def record_branch(name: str, author: str, when: datetime.datetime) -> int:
    """Link a new branch to the tickets its name names."""
    return _link(
        CodeReference.Kind.BRANCH,
        name,
        _keys(name, any_case=True),
        {
            'url': f'https://github.com/{settings.GILDE_BOARD_GITHUB_REPOSITORY}/tree/{name}',
            'title': name[:300],
            'author': author[:200],
            'happened_at': when,
        },
    )


def commits_from_push(payload: dict) -> list[dict]:
    """The commits of a push to the default branch; none for a push to any other branch."""
    if payload.get('ref') != f'refs/heads/{payload["repository"]["default_branch"]}':
        return []
    return [
        {
            'sha': commit['id'],
            'message': commit['message'],
            'url': commit['url'],
            'author': commit['author']['name'],
            'committed_at': datetime.datetime.fromisoformat(commit['timestamp']),
        }
        for commit in payload.get('commits', [])
    ]


def handle_event(event: str, payload: dict) -> int:
    """Record what a webhook delivery says; how many links are new. Other repositories, and events
    other than a push, a pull request change or a new branch, record nothing."""
    if payload.get('repository', {}).get('full_name') != settings.GILDE_BOARD_GITHUB_REPOSITORY:
        return 0
    if event == 'push':
        return record_commits(commits_from_push(payload))
    if event == 'pull_request' and payload.get('action') in PULL_REQUEST_ACTIONS:
        return record_pull_request(payload['pull_request'])
    if event == 'create' and payload.get('ref_type') == 'branch':
        # The event carries no time of its own; it arrives as the branch is pushed.
        return record_branch(payload['ref'], payload['sender']['login'], timezone.now())
    return 0


def _get(path: str, params: dict | None = None) -> requests.Response:
    response = requests.get(
        f'{API_URL}{path}',
        params=params,
        headers={
            'Authorization': f'Bearer {settings.GILDE_BOARD_GITHUB_TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        },
        timeout=30,
    )
    response.raise_for_status()
    return response


def _pages(path: str, params: dict) -> Iterator[list[dict]]:
    params = {**params, 'per_page': PAGE_SIZE, 'page': 1}
    while page := _get(path, params).json():
        yield page
        params['page'] += 1


def default_branch_commits(since: datetime.date | None = None) -> Iterator[list[dict]]:
    """The default branch's commits, newest first, a page at a time."""
    repository = settings.GILDE_BOARD_GITHUB_REPOSITORY
    params = {'sha': _get(f'/repos/{repository}').json()['default_branch']}
    if since:
        params['since'] = f'{since.isoformat()}T00:00:00Z'
    for page in _pages(f'/repos/{repository}/commits', params):
        yield [
            {
                'sha': item['sha'],
                'message': item['commit']['message'],
                'url': item['html_url'],
                'author': item['commit']['author']['name'],
                'committed_at': datetime.datetime.fromisoformat(item['commit']['author']['date']),
            }
            for item in page
        ]


def pull_requests(since: datetime.date | None = None) -> Iterator[list[dict]]:
    """Every pull request, open or not, newest first, a page at a time; from `since` on if given."""
    params = {'state': 'all', 'sort': 'created', 'direction': 'desc'}
    for page in _pages(f'/repos/{settings.GILDE_BOARD_GITHUB_REPOSITORY}/pulls', params):
        recent = [item for item in page if not since or datetime.date.fromisoformat(item['created_at'][:10]) >= since]
        if not recent:
            return
        yield recent
