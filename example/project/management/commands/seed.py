"""Fill the example project with a person to sign in as and a board to look at."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as UserGroup
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

from gilde.board.models import Column, Group, Relation, Ticket

DEMO_USER = 'demo'
DEMO_PASSWORD = 'demo'
COLUMNS = (
    ('To do', Column.Category.TODO),
    ('Doing', Column.Category.IN_PROGRESS),
    ('Review', Column.Category.IN_PROGRESS),
    ('Done', Column.Category.DONE),
)


class Command(BaseCommand):
    help = f'Make the user {DEMO_USER} (password {DEMO_PASSWORD}), a colleague, and a board with a few tickets.'

    def handle(self, *args, **options):
        users = get_user_model().objects
        demo = users.filter(username=DEMO_USER).first() or users.create_superuser(
            DEMO_USER, 'demo@example.com', DEMO_PASSWORD, first_name='Demo', last_name='User'
        )
        ann = users.filter(username='ann').first() or users.create_user(
            'ann', 'ann@example.com', first_name='Ann', last_name='Smith'
        )
        # Who may use the board is a permission, given here as a host project would: through a group.
        team, _ = UserGroup.objects.get_or_create(name='Team')
        team.permissions.add(Permission.objects.get(content_type__app_label='gilde_board', codename='use'))
        ann.groups.add(team)
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
