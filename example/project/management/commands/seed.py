"""Fill the example project with a person to sign in as, a board and a wiki to look at."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as UserGroup
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

from datagroceries.board.models import Column, Group, Relation, Ticket
from datagroceries.wiki.models import Page

DEMO_USER = 'demo'
DEMO_PASSWORD = 'demo'
COLUMNS = (
    ('To do', Column.Category.TODO),
    ('Doing', Column.Category.IN_PROGRESS),
    ('Review', Column.Category.IN_PROGRESS),
    ('Done', Column.Category.DONE),
)


class Command(BaseCommand):
    help = (
        f'Make the user {DEMO_USER} (password {DEMO_PASSWORD}), a colleague, a board with a few tickets and a wiki '
        'with a few pages.'
    )

    def handle(self, *args, **options):
        users = get_user_model().objects
        demo = users.filter(username=DEMO_USER).first() or users.create_superuser(
            DEMO_USER, 'demo@example.com', DEMO_PASSWORD, first_name='Demo', last_name='User'
        )
        ann = users.filter(username='ann').first() or users.create_user(
            'ann', 'ann@example.com', first_name='Ann', last_name='Smith'
        )
        # Who may use the board and the wiki is a permission each, given as a host project would: through a group.
        team, _ = UserGroup.objects.get_or_create(name='Team')
        uses = Permission.objects.filter(content_type__app_label__in=('dg_board', 'dg_wiki'), codename='use')
        team.permissions.add(*uses)
        ann.groups.add(team)
        self.seed_wiki(demo)
        if Group.objects.exists():
            self.stdout.write('The board has groups already; nothing more to seed.')
            return
        group = Group.objects.create(name='Product', slug='product')
        columns = [
            Column.objects.create(group=group, name=name, category=category, position=position)
            for position, (name, category) in enumerate(COLUMNS)
        ]
        tickets = []
        for title, column, assignee in (
            ('Sign up with an email address', columns[0], None),
            ('Show prices per month', columns[0], ann),
            ('Export the report as CSV', columns[1], demo),
            ('Fix the date in the footer', columns[2], ann),
            ('Write the onboarding guide', columns[3], demo),
        ):
            ticket = Ticket(title=title, creator=demo, assignee=assignee, description=f'About: {title.lower()}.')
            ticket.move_to(column)
            tickets.append(ticket)
        Relation.objects.create(source=tickets[0], target=tickets[1], type=Relation.Type.BLOCKS)
        self.stdout.write(f'Seeded. Sign in at /admin/ as {DEMO_USER} with password {DEMO_PASSWORD}.')

    def seed_wiki(self, author):
        if Page.objects.exists():
            return
        engineering = Page.objects.create(
            title='Engineering', creator=author, position=1, body=ENGINEERING, folder=True
        )
        Page.objects.create(title='Deploying', parent=engineering, creator=author, position=1, body=DEPLOYING)
        Page.objects.create(title='Onboarding', creator=author, position=2, body=ONBOARDING)


ENGINEERING = """How we build the product, and the pages about each part of it.
"""
DEPLOYING = """## Before

- The tests pass on the main branch.
- The changelog says what changes.

## Deploying

1. Pull on the server.
2. Install the requirements, migrate and collect the static files.
3. Restart the service.

## After

Check the site, and the errors of the last ten minutes.
"""
ONBOARDING = """Welcome to the team. This page lists what to do in your first week.

- [ ] Sign in to the board and the wiki.
- [ ] Read how we work in [[/Engineering]], and how a release goes out in [[/Engineering/Deploying]].
- [ ] Add yourself to [[/Who is who]].
- [ ] Pick up a ticket with a colleague.
"""
