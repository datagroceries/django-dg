"""What a visitor finds: a small team, two groups of tickets that show what the board does, a few wiki
pages beside them, and a ticket of their own that suggests what to try."""

import contextlib
import types

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as UserGroup
from django.contrib.auth.models import Permission
from django.db import transaction

from datagroceries.board.models import Column, Comment, Group, Label, Relation, Ticket, Watcher
from datagroceries.core import history
from datagroceries.wiki.models import Comment as PageComment
from datagroceries.wiki.models import Page, TopText
from datagroceries.wiki.models import Watcher as PageWatcher

# The user group whose members may use the board and the wiki: the team and every visitor.
MEMBERS = 'Members'
TEAM = (
    ('ann', 'Ann', 'Smith'),
    ('bob', 'Bob', 'Jansen'),
    ('chloe', 'Chloé', 'Martin'),
)


@contextlib.contextmanager
def acting_as(user, agent: str | None = None):
    """Records the changes made inside as `user`'s, and as made through `agent` ("via Claude") if given."""
    token = types.SimpleNamespace(name=agent) if agent else None
    with history.recording(types.SimpleNamespace(user=user, auth=token)):
        yield


def ticket(column, title, creator, *, labels=(), **fields):
    made = Ticket(title=title, creator=creator, **fields)
    made.move_to(column)
    made.labels.set(Label.objects.get_or_create(name=name)[0] for name in labels)
    for person in {creator, made.assignee} - {None}:
        Watcher.objects.get_or_create(ticket=made, user=person)
    return made


def comment(on, author, body, *, parent=None, sets_blocked=None):
    Watcher.objects.get_or_create(ticket=on, user=author)
    return Comment.objects.create(ticket=on, author=author, body=body, parent=parent, sets_blocked=sets_blocked)


@transaction.atomic
def seed():
    """Fills an empty database."""
    users = get_user_model().objects
    members = UserGroup.objects.create(name=MEMBERS)
    members.permissions.add(
        *Permission.objects.filter(content_type__app_label__in=('dg_board', 'dg_wiki'), codename='use')
    )
    ann, bob, chloe = (users.create_user(username, first_name=first, last_name=last) for username, first, last in TEAM)
    members.user_set.add(ann, bob, chloe)

    website = Group.objects.create(name='Website', slug='website', position=0)
    todo, doing, review, done = (
        Column.objects.create(group=website, name=name, category=category, position=position)
        for position, (name, category) in enumerate(
            (
                ('To do', Column.Category.TODO),
                ('Doing', Column.Category.IN_PROGRESS),
                ('Review', Column.Category.IN_PROGRESS),
                ('Done', Column.Category.DONE),
            )
        )
    )
    support = Group.objects.create(name='Support', slug='support', position=1)
    new, waiting, solved = (
        Column.objects.create(group=support, name=name, category=category, position=position)
        for position, (name, category) in enumerate(
            (
                ('New', Column.Category.TODO),
                ('Waiting for the customer', Column.Category.IN_PROGRESS),
                ('Solved', Column.Category.DONE),
            )
        )
    )

    with acting_as(chloe):
        pricing = ticket(
            doing,
            'Redesign the pricing page',
            chloe,
            assignee=chloe,
            size='weeks',
            labels=['design'],
            description=(
                'Visitors cannot tell the plans apart. The new page shows:\n\n'
                '- prices per month and per year\n'
                '- a table that compares the plans\n'
                '- one button per plan\n\n'
                'The subtasks below are the pieces.'
            ),
        )
        table = ticket(review, 'A table that compares the plans', chloe, assignee=chloe, size='days', labels=['design'])
    with acting_as(bob):
        prices = ticket(todo, 'Show prices per month and per year', bob, assignee=bob, size='days')
        ticket(done, 'The footer still shows last year', bob, assignee=bob, size='hours', labels=['bug'])
    with acting_as(chloe):
        for child in (table, prices):
            Relation.objects.create(source=pricing, target=child, type=Relation.Type.PARENT_OF)

    with acting_as(ann):
        signup = ticket(
            todo,
            'Sign up with an email address',
            ann,
            size='days',
            labels=['feature'],
            description='Today an account needs a Google login. Many customers asked for plain email.',
        )
        mail = ticket(doing, 'Choose a provider for the sign-up mails', ann, assignee=ann, size='hours')
        Relation.objects.create(source=mail, target=signup, type=Relation.Type.BLOCKS)
    with acting_as(bob):
        question = comment(mail, bob, 'Postmark or Amazon SES? Both have an EU region. @ann, any preference?')
    with acting_as(ann):
        comment(mail, ann, 'Postmark: its bounce handling is simpler, and the volume is small.', parent=question)

    # What an agent did: written by Ann's Claude, and it says so in the history.
    with acting_as(ann, agent='Claude'):
        export = ticket(
            todo,
            'Export the monthly report as CSV',
            ann,
            labels=['feature'],
            size='days',
            description=(
                'Three customers asked this week (see the support group). The report page gets an '
                '**Export** button that downloads the same rows as CSV, with a header row and the dates '
                'as YYYY-MM-DD.'
            ),
        )
        comment(export, ann, 'Linked the support ticket that asks for it; the other two came in by phone.')

    with acting_as(bob):
        move = ticket(
            todo,
            'Move the site to the new server',
            bob,
            assignee=bob,
            size='days',
            description='The new server is ordered; the move waits until it is there.',
        )
        comment(move, bob, 'Waiting for the hosting company to deliver the server.', sets_blocked=True)
        move.is_blocked = True
        move.save()

    with acting_as(ann):
        csv_question = ticket(
            new,
            'Customer asks: can I download my report?',
            ann,
            description='From an email by a customer: "I want to put the monthly numbers in my own spreadsheet."',
        )
        ticket(waiting, 'Login fails on an old iPad', ann, assignee=bob, labels=['bug'])
        ticket(solved, 'Invoice sent to the wrong address', ann, assignee=ann)
    with acting_as(ann, agent='Claude'):
        Relation.objects.create(source=csv_question, target=export, type=Relation.Type.RELATES_TO)

    seed_wiki(ann, bob, chloe, move)


def page(title, creator, body, *, parent=None, position):
    made = Page.objects.create(title=title, parent=parent, body=body, creator=creator, position=position)
    PageWatcher.objects.create(page=made, user=creator)
    return made


def seed_wiki(ann, bob, chloe, move):
    """A small tree of pages, a folder with two pages in it: links between them, one relative and one to a page
    nobody wrote yet, a ticket's key, so the ticket lists the page, a second version and a comment."""
    with acting_as(bob):
        engineering = page('Engineering', bob, ENGINEERING, position=1)
        # A folder from the start, without a version saying it became one.
        Page.objects.filter(pk=engineering.pk).update(folder=True)
        engineering.folder = True
        deploying = page('Deploying', bob, DEPLOYING.format(check='', move=move.key), parent=engineering, position=1)
        page('Rollback', bob, ROLLBACK, parent=engineering, position=2)
    with acting_as(ann):
        page('Onboarding', ann, ONBOARDING, position=2)
        TopText.objects.create(body=WELCOME)
    # A second version, so the page's history has two to compare.
    with acting_as(chloe):
        deploying.body = DEPLOYING.format(check=CHECK, move=move.key)
        deploying.save()
        PageWatcher.objects.create(page=deploying, user=chloe)
        PageComment.objects.create(
            page=deploying, author=chloe, body='Added what to check after a deploy. @bob, does that match what you do?'
        )


ENGINEERING = """How we build and run the website. The pages under this one say how a release goes out,
and how to take it back.
"""
DEPLOYING = """## Before

- The tests pass on the main branch.
- The changelog says what changes.

## Deploying

1. Pull on the server.
2. Install the requirements, migrate and collect the static files.
3. Restart the service.

## After

Check the site, and the errors of the last ten minutes.{check}

Something wrong? Go back as [[Rollback]] says.

The new server changes these steps: see {move}.
"""
CHECK = ' Open the pricing page and sign up once, as a customer would.'
ROLLBACK = """1. Check out the release before on the server.
2. Install its requirements. Migrations stay: a release never removes a column the one before it needs.
3. Restart the service, and say so on the ticket of the release.
"""
WELCOME = """The team's own knowledge, written by people and agents together. New here? Start at
[[Onboarding]]; how we build and ship is in [[Engineering]].
"""
ONBOARDING = """Welcome to the team. This page lists what to do in your first week.

- [ ] Sign in to the board and the wiki.
- [ ] Read how a release goes out in [[/Engineering/Deploying]].
- [ ] Add yourself to [[/Who is who]].
- [ ] Pick up a ticket with a colleague.
"""


def welcome(visitor):
    """A ticket of the visitor's own, at the top of To do, that suggests what to try: in the first group's
    to-do column, and none when no group has a column. Visitors may not change the groups (people.py),
    but the superuser may."""
    ann = get_user_model().objects.get(username='ann')
    group = Group.objects.filter(columns__isnull=False).first()
    column = group and group.intake_column()
    if column is None:
        return None
    first = column.tickets.first()
    with acting_as(ann):
        made = Ticket(
            title=f'Welcome, {visitor.first_name} {visitor.last_name}: things to try',
            creator=ann,
            assignee=visitor,
            size='hours',
            description=(
                'This ticket is yours. A few things to try:\n\n'
                '- Drag it to **Doing** on the board.\n'
                '- Leave a comment below that mentions @ann.\n'
                '- Open **Connect an agent** on the board, connect Claude, and ask it: *"What is assigned to '
                'me on the board? Move my welcome ticket to Done and say so in a comment."*\n'
                "- Then look at this ticket's history: Claude's changes say they were made through Claude.\n"
                "- Read the team's wiki page on releases, [[/Engineering/Deploying]], and edit it: the ticket it names "
                'lists it.\n\n'
                'Everything here, your account too, is gone tomorrow morning.'
            ),
        )
        made.move_to(column, before=first)
        Watcher.objects.create(ticket=made, user=visitor)
    return made
