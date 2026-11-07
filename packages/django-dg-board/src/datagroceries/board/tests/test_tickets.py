import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from datagroceries.board.activity import build_feed
from datagroceries.board.forms import fingerprint
from datagroceries.board.models import RANK_GAP, Attachment, Column, Comment, Group, Label, Relation, Ticket, Watcher
from datagroceries.board.templatetags.dg_board import avatar
from datagroceries.board.tests import member
from datagroceries.core import backlinks
from datagroceries.core.people import People
from datagroceries.core.templatetags.dg_core import render_markdown
from datagroceries.core.tests import addressed


class FirstNamePeople(People):
    """People known by their first name, with a photo."""

    def handle(self, user):
        return user.first_name.lower() or None

    def avatar_url(self, user, size):
        return f'/photos/{user.username}-{size}.png'


class TicketTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = member(
            username='anna',
            email='anna@example.com',
            first_name='Anna',
            last_name='Tester',
        )
        cls.group = Group.objects.create(name='Platform', slug='platform')
        cls.todo = Column.objects.create(group=cls.group, name='To do', category=Column.Category.TODO, position=0)
        cls.doing = Column.objects.create(
            group=cls.group,
            name='Doing',
            category=Column.Category.IN_PROGRESS,
            position=1,
        )
        cls.done = Column.objects.create(group=cls.group, name='Done', category=Column.Category.DONE, position=2)

    def setUp(self):
        self.client.force_login(self.user)

    def make_ticket(self, title='A ticket', column=None, **fields):
        ticket = Ticket(title=title, creator=self.user, **fields)
        ticket.move_to(column or self.todo)
        return ticket


class KeyTests(TicketTestCase):
    def test_the_page_lives_at_the_key(self):
        ticket = self.make_ticket()

        response = self.client.get(f'/dg/board/EX-{ticket.pk}/')

        self.assertEqual(ticket.key, f'EX-{ticket.pk}')
        self.assertContains(response, 'A ticket')

    def test_the_key_stays_when_the_ticket_changes_group(self):
        other = Group.objects.create(name='Sales', slug='sales')
        backlog = Column.objects.create(group=other, name='Backlog', category=Column.Category.TODO)
        ticket = self.make_ticket()
        key = ticket.key

        ticket.move_to(backlog)

        self.assertEqual(Ticket.objects.get(pk=ticket.pk).key, key)


class MoveTests(TicketTestCase):
    def test_a_drop_lands_above_the_card_it_was_dropped_on(self):
        self.make_ticket('1')
        second, third = self.make_ticket('2'), self.make_ticket('3')

        response = self.client.post(
            reverse('dg_board:ticket_move', args=[third.pk]),
            {'column': self.todo.pk, 'before': second.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.todo.tickets.values_list('title', flat=True)), ['1', '3', '2'])

    def test_a_drop_without_a_card_below_goes_to_the_end(self):
        self.make_ticket('1', column=self.doing)
        ticket = self.make_ticket('2')

        self.client.post(reverse('dg_board:ticket_move', args=[ticket.pk]), {'column': self.doing.pk})

        self.assertEqual(list(self.doing.tickets.values_list('title', flat=True)), ['1', '2'])

    def test_a_done_column_closes_the_ticket_and_leaving_it_reopens(self):
        ticket = self.make_ticket()

        ticket.move_to(self.done)
        self.assertIsNotNone(ticket.closed_at)
        ticket.move_to(self.doing)
        self.assertIsNone(ticket.closed_at)

    def test_a_new_place_in_the_same_column_writes_no_history(self):
        neighbour, mover = self.make_ticket('neighbour'), self.make_ticket('mover')
        records_before = mover.history.count() + neighbour.history.count()

        mover.move_to(self.todo, before=neighbour)

        self.assertEqual(mover.history.count() + neighbour.history.count(), records_before)
        self.assertEqual(list(self.todo.tickets.values_list('title', flat=True)), ['mover', 'neighbour'])

    def test_a_drop_between_cards_keeps_the_order_of_all_tickets(self):
        # One order of all tickets: in it, the card lands just above the one it was dropped on, so a
        # ticket in another column between the two keeps its place relative to both.
        first, elsewhere, second = (
            self.make_ticket('1'),
            self.make_ticket('x', column=self.doing),
            self.make_ticket('2'),
        )
        mover = self.make_ticket('mover', column=self.doing)

        self.client.post(
            reverse('dg_board:ticket_move', args=[mover.pk]), {'column': self.todo.pk, 'before': second.pk}
        )

        self.assertEqual(
            list(Ticket.objects.values_list('title', flat=True)),
            [first.title, elsewhere.title, 'mover', second.title],
        )

    def test_a_status_change_puts_the_ticket_at_the_top_of_its_new_column(self):
        self.make_ticket('1', column=self.doing)
        ticket = self.make_ticket('2')

        self.client.post(
            reverse('dg_board:ticket_update', args=[ticket.pk]),
            {'field': 'column', 'value': self.doing.pk},
        )

        self.assertEqual(list(self.doing.tickets.values_list('title', flat=True)), ['2', '1'])

    def test_a_used_up_gap_renumbers_every_ticket_in_order(self):
        top, bottom = self.make_ticket('top'), self.make_ticket('bottom')
        Ticket.objects.filter(pk=bottom.pk).update(rank=top.rank + 1)

        self.make_ticket('middle').move_to(self.todo, before=bottom)

        self.assertEqual(list(Ticket.objects.values_list('title', flat=True)), ['top', 'middle', 'bottom'])
        self.assertEqual(Ticket.objects.get(pk=bottom.pk).rank - Ticket.objects.get(pk=top.pk).rank, RANK_GAP)


class RelationTests(TicketTestCase):
    def add_relation(self, ticket, kind, other):
        return self.client.post(ticket.get_absolute_url(), {'action': 'relation', 'kind': kind, 'other': other.key})

    def test_child_of_is_stored_as_the_parent_s_relation(self):
        parent, child = self.make_ticket('parent'), self.make_ticket('child')

        self.add_relation(child, 'child_of', parent)

        self.assertTrue(Relation.objects.filter(source=parent, target=child, type=Relation.Type.PARENT_OF).exists())

    def test_a_ticket_has_at_most_one_parent(self):
        child = self.make_ticket('child')
        self.add_relation(child, 'child_of', self.make_ticket('first parent'))

        response = self.add_relation(child, 'child_of', self.make_ticket('second parent'))

        self.assertContains(response, 'only one parent')
        self.assertEqual(child.incoming_relations.filter(type=Relation.Type.PARENT_OF).count(), 1)

    def test_blocks_cannot_loop(self):
        a, b, c = self.make_ticket('a'), self.make_ticket('b'), self.make_ticket('c')
        self.add_relation(a, 'blocks', b)
        self.add_relation(b, 'blocks', c)

        response = self.add_relation(c, 'blocks', a)

        self.assertContains(response, 'loop')

    def test_a_child_is_created_from_a_title(self):
        parent = self.make_ticket('parent', column=self.doing)

        response = self.client.post(parent.get_absolute_url(), {'action': 'child', 'title': 'first step'})

        child = Ticket.objects.get(title='first step')
        self.assertRedirects(response, parent.get_absolute_url())
        self.assertEqual((child.column, child.creator), (self.todo, self.user))
        self.assertTrue(Relation.objects.filter(source=parent, target=child, type=Relation.Type.PARENT_OF).exists())

    def test_a_child_skips_an_icebox_for_the_to_do_column_nearest_the_work(self):
        group = Group.objects.create(name='Imported', slug='imported')
        Column.objects.create(group=group, name='Icebox', category=Column.Category.TODO, position=0)
        todo = Column.objects.create(group=group, name='To do', category=Column.Category.TODO, position=1)
        doing = Column.objects.create(group=group, name='Doing', category=Column.Category.IN_PROGRESS, position=2)
        parent = self.make_ticket('parent', column=doing)

        self.client.post(parent.get_absolute_url(), {'action': 'child', 'title': 'next step'})

        self.assertEqual(Ticket.objects.get(title='next step').column, todo)

    def test_related_tickets_are_listed_and_reordered_in_the_board_s_order(self):
        parent = self.make_ticket('parent')
        first, second = self.make_ticket('first', column=self.doing), self.make_ticket('second')
        for child in (second, first):
            Relation.objects.create(source=parent, target=child, type=Relation.Type.PARENT_OF)
        page = self.client.get(parent.get_absolute_url()).content
        self.assertLess(page.index(b'>first<'), page.index(b'>second<'))

        response = self.client.post(reverse('dg_board:ticket_reorder', args=[second.pk]), {'before': first.pk})

        self.assertEqual(response.status_code, 200)
        page = self.client.get(parent.get_absolute_url()).content
        self.assertLess(page.index(b'>second<'), page.index(b'>first<'))
        self.assertEqual(Ticket.objects.get(pk=second.pk).column, self.todo)

    def test_a_row_dropped_last_goes_just_below_the_last_one(self):
        first, second = self.make_ticket('1'), self.make_ticket('2')
        self.make_ticket('3')

        self.client.post(reverse('dg_board:ticket_reorder', args=[first.pk]), {'after': second.pk})

        self.assertEqual(list(Ticket.objects.values_list('title', flat=True)), ['2', '1', '3'])

    def test_the_relations_table_marks_blocked_tickets_and_counts_done_ones(self):
        ticket = self.make_ticket('main')
        blocked = self.make_ticket('flagged', is_blocked=True)
        Relation.objects.create(source=ticket, target=blocked, type=Relation.Type.RELATES_TO)
        finished = self.make_ticket('finished', column=self.done)
        Relation.objects.create(source=ticket, target=finished, type=Relation.Type.RELATES_TO)

        response = self.client.get(ticket.get_absolute_url())

        self.assertContains(response, 'title="Blocked"')
        self.assertContains(response, 'Hide done (1)')

    def test_a_ticket_is_deleted_with_its_comments_and_relations(self):
        ticket, other = self.make_ticket('A mistake'), self.make_ticket('Stays')
        Relation.objects.create(source=ticket, target=other, type=Relation.Type.RELATES_TO)
        Comment.objects.create(ticket=ticket, author=self.user, body='Oops')

        response = self.client.post(ticket.get_absolute_url(), {'action': 'delete'})

        self.assertRedirects(response, f'{reverse("dg_board:board")}?group=platform', fetch_redirect_response=False)
        self.assertFalse(Ticket.objects.filter(pk=ticket.pk).exists())
        self.assertFalse(Relation.objects.exists())
        self.assertFalse(Comment.objects.exists())
        self.assertTrue(Ticket.objects.filter(pk=other.pk).exists())

    @mock.patch('django.db.models.fields.files.FieldFile.delete')
    def test_a_deleted_ticket_s_files_go_from_storage_once_it_is_gone(self, delete_file):
        ticket = self.make_ticket('With a file')
        Attachment.objects.create(
            ticket=ticket,
            file='dg_board/x.png',
            name='x.png',
            content_type='image/png',
            size=1,
            uploaded_by=self.user,
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(ticket.get_absolute_url(), {'action': 'delete'})

        self.assertFalse(Attachment.objects.filter(ticket_id=ticket.pk).exists())
        self.assertTrue(delete_file.called)

    def test_the_relations_table_shows_who_made_a_related_ticket_and_when(self):
        ticket = self.make_ticket('main')
        other = self.make_ticket('related')
        Ticket.objects.filter(pk=other.pk).update(
            created_at=datetime.datetime(2026, 9, 28, 22, 30, tzinfo=datetime.UTC),
        )
        Relation.objects.create(source=ticket, target=other, type=Relation.Type.RELATES_TO)

        response = self.client.get(ticket.get_absolute_url())

        # 22:30 UTC is the next day in Amsterdam, where the page shows its times.
        self.assertContains(response, 'title="Created by Anna Tester, 2026-09-29 00:30"')
        self.assertContains(response, '29 Sep 2026')

    def test_only_an_open_blocker_blocks(self):
        blocker, ticket = self.make_ticket('blocker'), self.make_ticket('blocked')
        self.add_relation(blocker, 'blocks', ticket)
        self.assertEqual(list(ticket.open_blockers()), [blocker])

        blocker.move_to(self.done)

        self.assertEqual(list(ticket.open_blockers()), [])


class OpenOnBoardTests(TicketTestCase):
    def add_children(self, parent, *children):
        for child in children:
            Relation.objects.create(source=parent, target=child, type=Relation.Type.PARENT_OF)

    def test_open_on_board_shows_the_ticket_and_everything_under_it(self):
        parent, step = self.make_ticket('The epic'), self.make_ticket('A step')
        self.add_children(parent, step)
        self.add_children(step, self.make_ticket('A smaller step'))
        self.make_ticket('Unrelated')
        board_url = f'{reverse("dg_board:board")}?group=platform&parent={parent.key}'
        link = f'href="{board_url.replace("&", "&amp;")}"'
        # Beside the heading of the subtasks.
        self.assertContains(self.client.get(parent.get_absolute_url()), link)

        board = self.client.get(board_url)

        for title in ('The epic', 'A step', 'A smaller step'):
            self.assertContains(board, f'>{title}</a>')
        self.assertNotContains(board, 'Unrelated')
        self.assertContains(board, f'<input type="hidden" name="parent" value="{parent.key}">')
        # A parent deleted since it was remembered is forgotten, with the rest of the remembered view.
        parent.delete()
        self.assertRedirects(self.client.get(board_url), reverse('dg_board:board'), fetch_redirect_response=False)
        self.assertNotIn('tickets_board', self.client.session)

    def test_open_on_board_and_a_card_s_subtask_count_open_the_ticket_s_own_group(self):
        other = Group.objects.create(name='Sales', slug='sales')
        backlog = Column.objects.create(group=other, name='Backlog', category=Column.Category.TODO)
        parent = self.make_ticket('The epic')
        self.add_children(parent, self.make_ticket('Elsewhere', column=backlog))
        link = f'href="{reverse("dg_board:board")}?group=platform&amp;parent={parent.key}"'

        self.assertContains(self.client.get(parent.get_absolute_url()), link)
        self.assertContains(self.client.get(f'{reverse("dg_board:board")}?group=all'), link)


class PeekTests(TicketTestCase):
    def test_a_card_s_title_and_a_related_ticket_open_in_the_quick_view(self):
        parent, child = self.make_ticket('parent'), self.make_ticket('child')
        Relation.objects.create(source=parent, target=child, type=Relation.Type.PARENT_OF)
        peek = f'data-tk-peek="{reverse("dg_board:ticket_peek", args=[child.key])}"'

        self.assertContains(self.client.get('/dg/board/?group=platform'), peek)
        self.assertContains(self.client.get(parent.get_absolute_url()), peek)

    def test_the_quick_view_shows_the_ticket_in_brief_with_the_newest_comments(self):
        ticket = self.make_ticket('Peek at me', description='**Bold** words', assignee=self.user)
        child = self.make_ticket('A step', column=self.done)
        Relation.objects.create(source=ticket, target=child, type=Relation.Type.PARENT_OF)
        for number in range(4):
            Comment.objects.create(ticket=ticket, author=self.user, body=f'Comment {number}')

        response = self.client.get(reverse('dg_board:ticket_peek', args=[ticket.key]))

        self.assertNotContains(response, '<html')
        self.assertContains(response, '<strong>Bold</strong>')
        self.assertContains(response, f'href="{ticket.get_absolute_url()}">Open ticket')
        self.assertContains(response, f'data-tk-copy-link="{ticket.get_absolute_url()}"')
        self.assertContains(response, f'data-tk-peek="{reverse("dg_board:ticket_peek", args=[child.key])}"')
        self.assertContains(response, 'Comment 3')
        self.assertNotContains(response, 'Comment 0')
        self.assertContains(response, 'All 4 comments')

    def test_a_key_that_names_no_ticket_is_not_found(self):
        self.assertEqual(self.client.get(reverse('dg_board:ticket_peek', args=['EX-999999'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('dg_board:ticket_peek', args=['nonsense'])).status_code, 404)


class BlockedTests(TicketTestCase):
    def test_blocking_needs_a_reason(self):
        ticket = self.make_ticket()

        response = self.client.post(ticket.get_absolute_url(), {'action': 'block', 'reason': ''})

        self.assertContains(response, 'Say why')
        ticket.refresh_from_db()
        self.assertFalse(ticket.is_blocked)

    def test_blocking_and_unblocking_leave_their_comments(self):
        ticket = self.make_ticket()

        self.client.post(ticket.get_absolute_url(), {'action': 'block', 'reason': 'Waiting for Elia'})
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_blocked)
        self.client.post(ticket.get_absolute_url(), {'action': 'block', 'reason': ''})

        ticket.refresh_from_db()
        self.assertFalse(ticket.is_blocked)
        self.assertEqual(
            list(ticket.comments.values_list('sets_blocked', 'body')),
            [(True, 'Waiting for Elia'), (False, '')],
        )


class CommentLinkTests(TicketTestCase):
    def test_every_comment_and_reply_can_be_linked_to(self):
        ticket = self.make_ticket()
        comment = Comment.objects.create(ticket=ticket, author=self.user, body='A comment')
        reply = Comment.objects.create(ticket=ticket, author=self.user, body='A reply', parent=comment)

        response = self.client.get(ticket.get_absolute_url())

        for pk in (comment.pk, reply.pk):
            with self.subTest(pk=pk):
                self.assertContains(response, f'id="comment-{pk}"')
                self.assertContains(response, f'data-tk-copy-link="#comment-{pk}"')


class AssigneeSelectTests(TicketTestCase):
    def test_unassign_and_assign_to_me_come_first(self):
        other = member(username='aaron', first_name='Aaron')
        ticket = self.make_ticket(assignee=other)

        html = self.client.get(ticket.get_absolute_url()).content.decode()

        unassign = html.index('{"choice": "Unassign"}')
        me = html.index('{"choice": "Assign to me"}')
        self.assertLess(unassign, me)
        self.assertLess(me, html.index(f'<option value="{other.pk}" selected>Aaron</option>'))


class EditTests(TicketTestCase):
    def edit_text(self, ticket, field, value, started_from):
        return self.client.post(
            ticket.get_absolute_url(),
            {'action': field, field: value, 'original': fingerprint(started_from)},
        )

    def update(self, ticket, field, *values):
        return self.client.post(reverse('dg_board:ticket_update', args=[ticket.pk]), {'field': field, 'value': values})

    def test_the_description_is_edited_in_place(self):
        ticket = self.make_ticket(description='old')

        response = self.edit_text(ticket, 'description', 'new', started_from='old')

        self.assertRedirects(response, ticket.get_absolute_url())
        ticket.refresh_from_db()
        self.assertEqual(ticket.description, 'new')

    def test_an_edit_of_text_someone_else_changed_is_refused(self):
        ticket = self.make_ticket(title='Original')
        self.edit_text(ticket, 'title', 'Theirs', started_from='Original')

        response = self.edit_text(ticket, 'title', 'Mine', started_from='Original')

        self.assertContains(response, 'changed the title while you were editing it')
        self.assertContains(response, 'value="Mine"')
        ticket.refresh_from_db()
        self.assertEqual(ticket.title, 'Theirs')

    def test_a_change_to_another_field_does_not_refuse_the_edit(self):
        ticket = self.make_ticket(description='old')
        self.update(ticket, 'size', 'days')

        self.edit_text(ticket, 'description', 'new', started_from='old')

        ticket.refresh_from_db()
        self.assertEqual((ticket.description, ticket.size), ('new', 'days'))

    def test_the_sidebar_saves_each_property(self):
        ticket = self.make_ticket()

        self.update(ticket, 'column', self.doing.pk)
        self.update(ticket, 'assignee', self.user.pk)
        self.update(ticket, 'size', 'days')
        self.update(ticket, 'labels', 'bug,ops')

        ticket.refresh_from_db()
        self.assertEqual((ticket.column, ticket.assignee, ticket.size), (self.doing, self.user, 'days'))
        self.assertEqual(sorted(ticket.labels.values_list('name', flat=True)), ['bug', 'ops'])
        lines = ' '.join(line for entry in build_feed(ticket) for line in entry.lines)
        self.assertIn('moved it from To do to Doing', lines)
        self.assertIn('set the size to Days', lines)
        self.assertIn('added label "bug"', lines)

    def test_a_new_group_puts_the_ticket_in_its_column_of_the_same_kind(self):
        other = Group.objects.create(name='Sales', slug='sales')
        Column.objects.create(group=other, name='Backlog', category=Column.Category.TODO, position=0)
        busy = Column.objects.create(group=other, name='Busy', category=Column.Category.IN_PROGRESS, position=1)
        ticket = self.make_ticket(column=self.doing)

        self.update(ticket, 'group', other.pk)

        ticket.refresh_from_db()
        self.assertEqual(ticket.column, busy)

    def test_a_column_of_another_group_is_refused(self):
        other = Group.objects.create(name='Sales', slug='sales')
        backlog = Column.objects.create(group=other, name='Backlog', category=Column.Category.TODO)
        ticket = self.make_ticket()

        response = self.update(ticket, 'column', backlog.pk)

        self.assertEqual(response.status_code, 404)

    def test_an_unknown_size_is_refused(self):
        ticket = self.make_ticket()

        self.assertEqual(self.update(ticket, 'size', 'years').status_code, 400)

    def test_a_reply_cannot_be_replied_to(self):
        ticket = self.make_ticket()
        comment = Comment.objects.create(ticket=ticket, author=self.user, body='first')
        reply = Comment.objects.create(ticket=ticket, author=self.user, body='second', parent=comment)

        response = self.client.post(
            ticket.get_absolute_url(),
            {'action': 'comment', 'body': 'third', 'parent': reply.pk},
        )

        self.assertContains(response, 'cannot be replied to')

    def test_a_column_with_tickets_cannot_be_deleted(self):
        self.make_ticket(column=self.doing)
        data = {
            'group-name': 'Platform',
            'group-slug': 'platform',
            'group-position': 0,
            'group-done_days': 14,
            'columns-TOTAL_FORMS': 4,
            'columns-INITIAL_FORMS': 3,
            'columns-MIN_NUM_FORMS': 0,
            'columns-MAX_NUM_FORMS': 1000,
        }
        for index, column in enumerate([self.todo, self.doing, self.done]):
            data |= {
                f'columns-{index}-id': column.pk,
                f'columns-{index}-name': column.name,
                f'columns-{index}-category': column.category,
                f'columns-{index}-position': column.position,
            }
        data['columns-1-DELETE'] = 'on'

        response = self.client.post(reverse('dg_board:group_edit', args=['platform']), data)

        self.assertContains(response, 'still holds tickets')
        self.assertTrue(Column.objects.filter(pk=self.doing.pk).exists())


class BoardTests(TicketTestCase):
    def test_a_new_ticket_starts_from_a_column_s_plus_and_c_takes_the_first(self):
        response = self.client.get('/dg/board/?group=platform')

        self.assertNotContains(response, 'New ticket</a>')
        self.assertContains(response, 'data-tk-new-ticket', count=3)
        self.assertContains(response, 'title="New ticket in To do (c)"')

    def test_a_group_board_and_the_all_groups_board_render(self):
        self.make_ticket('Visible ticket')

        self.assertContains(self.client.get('/dg/board/?group=platform'), 'Visible ticket')
        self.assertContains(self.client.get('/dg/board/?group=all&assignee=none'), 'Visible ticket')

    def test_done_tickets_stay_on_the_board_as_long_as_their_group_says(self):
        sales = Group.objects.create(name='Sales', slug='sales')
        sales_done = Column.objects.create(group=sales, name='Done', category=Column.Category.DONE)
        ten_days_ago = timezone.now() - datetime.timedelta(days=10)
        for title, column in (('Platform, done 10 days ago', self.done), ('Sales, done 10 days ago', sales_done)):
            Ticket.objects.filter(pk=self.make_ticket(title, column=column).pk).update(closed_at=ten_days_ago)
        Ticket.objects.filter(pk=self.make_ticket('Platform, done 5 days ago', column=self.done).pk).update(
            closed_at=timezone.now() - datetime.timedelta(days=5),
        )

        group_page = self.client.get(reverse('dg_board:group_edit', args=['platform']))
        self.assertContains(group_page, 'name="group-done_days" value="14"')
        data = {
            'group-name': 'Platform',
            'group-slug': 'platform',
            'group-position': 0,
            'group-done_days': 7,
            'columns-TOTAL_FORMS': 3,
            'columns-INITIAL_FORMS': 3,
        }
        for index, column in enumerate([self.todo, self.doing, self.done]):
            data |= {
                f'columns-{index}-id': column.pk,
                f'columns-{index}-name': column.name,
                f'columns-{index}-category': column.category,
                f'columns-{index}-position': column.position,
            }
        self.client.post(reverse('dg_board:group_edit', args=['platform']), data)

        self.assertEqual(Group.objects.get(pk=self.group.pk).done_days, 7)
        for board in ('platform', 'all'):
            page = self.client.get(f'/dg/board/?group={board}').content.decode()
            self.assertIn('Platform, done 5 days ago', page, board)
            self.assertNotIn('Platform, done 10 days ago', page, board)
        # Sales keeps the 14 days every group starts with.
        self.assertContains(self.client.get('/dg/board/?group=all'), 'Sales, done 10 days ago')

    def test_a_subtask_s_card_names_its_parent(self):
        parent, child = self.make_ticket('A parent'), self.make_ticket('A child')
        Relation.objects.create(source=parent, target=child, type=Relation.Type.PARENT_OF)

        response = self.client.get('/dg/board/?group=platform')

        self.assertContains(
            response,
            f'href="{parent.get_absolute_url()}" title="Subtask of {parent.key}: A parent"',
            count=1,
        )

    def test_a_card_s_label_filters_the_board_on_it(self):
        ticket = self.make_ticket('Labelled')
        ticket.labels.add(Label.objects.create(name='old board'))

        response = self.client.get('/dg/board/?group=platform')

        self.assertContains(response, f'href="{reverse("dg_board:board")}?group=platform&amp;label=old%20board"')

    def test_the_label_filter_can_ask_for_tickets_without_a_label(self):
        self.make_ticket('Bare')
        self.make_ticket('Tagged').labels.add(Label.objects.create(name='invoice'))
        self.make_ticket('Other tag').labels.add(Label.objects.create(name='ops'))

        bare = self.client.get('/dg/board/?group=platform&label=none')
        bare_or_invoice = self.client.get('/dg/board/?group=platform&label=none&label=invoice')

        self.assertContains(bare, 'Bare')
        self.assertNotContains(bare, 'Tagged')
        self.assertNotContains(bare, 'Other tag')
        self.assertContains(bare_or_invoice, 'Bare')
        self.assertContains(bare_or_invoice, 'Tagged')
        self.assertNotContains(bare_or_invoice, 'Other tag')

    def test_a_lane_can_fold_away(self):
        # The folding itself runs in the browser; the lane says which column it is, for it to remember.
        response = self.client.get('/dg/board/?group=platform')

        self.assertContains(response, f'<section class="tk-lane" data-lane="{self.todo.pk}">')
        self.assertContains(response, 'title="Collapse To do"')

    def test_show_top_level_or_parents_only(self):
        parent, child = self.make_ticket('A parent'), self.make_ticket('A child')
        self.make_ticket('Loose one')
        Relation.objects.create(source=parent, target=child, type=Relation.Type.PARENT_OF)

        top = self.client.get('/dg/board/?group=platform&show=top')
        parents = self.client.get('/dg/board/?group=platform&show=parents')

        self.assertContains(top, 'A parent')
        self.assertContains(top, 'Loose one')
        self.assertNotContains(top, 'A child')
        self.assertContains(parents, 'A parent')
        self.assertNotContains(parents, 'Loose one')
        self.assertNotContains(parents, 'A child')
        self.assertEqual(self.client.get('/dg/board/?group=platform&show=nonsense').status_code, 404)

    def test_filters_narrow_the_board(self):
        self.make_ticket('Mine', assignee=self.user)
        self.make_ticket('Nobody s')

        response = self.client.get('/dg/board/?group=platform&assignee=me')

        self.assertContains(response, 'Mine')
        self.assertNotContains(response, 'Nobody s')

    def test_the_creator_filter_narrows_the_board(self):
        colleague = member(username='colleague')
        self.make_ticket('Made by me')
        theirs = self.make_ticket('Made by a colleague')
        Ticket.objects.filter(pk=theirs.pk).update(creator=colleague)

        mine = self.client.get('/dg/board/?group=platform&creator=me')
        their_board = self.client.get(f'/dg/board/?group=platform&creator={colleague.pk}')

        self.assertContains(mine, 'Made by me')
        self.assertNotContains(mine, 'Made by a colleague')
        self.assertContains(their_board, 'Made by a colleague')
        self.assertNotContains(their_board, 'Made by me')


class NamedInTests(TicketTestCase):
    """What names a ticket in another app's text (datagroceries.core.backlinks), as the wiki's pages do."""

    def setUp(self):
        super().setUp()
        self.ticket = self.make_ticket()

    def register(self, scope):
        def find(name):
            return [backlinks.Backlink(f'Notes on {name}', '/notes/')] if name == self.ticket.key else []

        source = backlinks.Source(scope, 'Notes', find)
        backlinks.register(source)
        self.addCleanup(backlinks.SOURCES.remove, source)

    def test_the_ticket_lists_the_places_that_name_it(self):
        self.register('board')

        response = self.client.get(self.ticket.get_absolute_url())

        self.assertContains(response, '<div class="tk-panel-title">Notes</div>', html=True)
        self.assertContains(response, f'<a href="/notes/">Notes on {self.ticket.key}</a>', html=True)

    def test_an_area_the_person_may_not_use_shows_nothing(self):
        self.register('wiki')

        self.assertNotContains(self.client.get(self.ticket.get_absolute_url()), 'Notes on')


class AttachmentTests(TicketTestCase):
    def test_an_html_file_is_served_as_a_download(self):
        ticket = self.make_ticket()
        self.client.post(
            ticket.get_absolute_url(),
            {'action': 'attachment', 'file': SimpleUploadedFile('page.html', b'<script></script>', 'text/html')},
        )
        attachment = ticket.attachments.get()

        response = self.client.get(attachment.get_absolute_url())

        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_an_image_pasted_before_the_ticket_existed_is_linked_on_create(self):
        upload = SimpleUploadedFile('shot.png', b'\x89PNG', 'image/png')
        path = self.client.post(reverse('dg_board:attachment_upload'), {'image': upload}).json()['data']['filePath']

        self.client.post(
            reverse('dg_board:ticket_create'),
            {'title': 'With image', 'description': f'![shot]({path})', 'column': self.todo.pk},
        )

        self.assertEqual(Attachment.objects.get().ticket, Ticket.objects.get(title='With image'))

    def test_an_uploaded_image_s_address_ends_in_its_name_and_the_old_one_still_works(self):
        # The Markdown editor inserts an upload as an image only when its URL ends in an image extension.
        upload = SimpleUploadedFile('Schermafbeelding om 11.29 (1).PNG', b'\x89PNG', 'image/png')

        path = self.client.post(reverse('dg_board:attachment_upload'), {'image': upload}).json()['data']['filePath']

        attachment = Attachment.objects.get()
        self.assertEqual(path, f'/dg/board/attachments/{attachment.pk}/schermafbeelding-om-1129-1.png')
        for url in (path, f'/dg/board/attachments/{attachment.pk}/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url)['Content-Type'], 'image/png')

    def test_the_editor_upload_accepts_images_only(self):
        upload = SimpleUploadedFile('page.svg', b'<svg/>', 'image/svg+xml')

        response = self.client.post(reverse('dg_board:attachment_upload'), {'image': upload})

        self.assertEqual(response.json(), {'error': 'typeNotAllowed'})


class AvatarTests(TicketTestCase):
    def test_without_a_photo_the_avatar_shows_initials(self):
        self.assertIn('>AT</span>', avatar(self.user))

    @override_settings(DG_PEOPLE='datagroceries.board.tests.test_tickets.FirstNamePeople')
    def test_the_host_project_s_image_is_shown_when_it_has_one(self):
        html = avatar(self.user)

        self.assertIn('<img', html)
        self.assertIn('src="/photos/anna-64.png"', html)

    @override_settings(DG_PEOPLE='datagroceries.board.tests.test_tickets.FirstNamePeople')
    def test_the_editors_know_whom_a_mention_reaches(self):
        # Without a handle nobody is reached by a mention, so nobody is offered for one.
        member(username='nameless')
        people = '<script id="dg-mention-people" type="application/json">[{"handle": "anna", "name": "Anna Tester"}]'

        self.assertContains(self.client.get(self.make_ticket().get_absolute_url()), people)
        self.assertContains(self.client.get(reverse('dg_board:ticket_create')), people)

    def test_a_card_names_its_assignee(self):
        self.make_ticket('Assigned', assignee=self.user)

        response = self.client.get('/dg/board/?group=platform')

        self.assertContains(response, '<span class="tk-assignee-name">Anna</span>', count=1)

    def test_a_card_is_assigned_from_the_board_to_anyone_and_shows_it_at_once(self):
        bob = member(
            username='bob',
            email='bob@example.com',
            first_name='Bob',
        )
        ticket = self.make_ticket('Unassigned')
        update = reverse('dg_board:ticket_update', args=[ticket.pk])

        board = self.client.get('/dg/board/?group=platform')

        # The picker offers everyone, not only the people with a ticket on the board as the filter does.
        self.assertContains(board, f'<option value="{bob.pk}">Bob</option>')
        self.assertContains(board, f'data-assign-url="{update}" data-assignee=""')
        assigned = self.client.post(update, {'field': 'assignee', 'value': bob.pk}).json()['card_assignee']
        self.assertIn(f'data-assignee="{bob.pk}"', assigned)
        self.assertIn('<span class="tk-assignee-name">Bob</span>', assigned)
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).assignee, bob)
        unassigned = self.client.post(update, {'field': 'assignee', 'value': ''}).json()['card_assignee']
        self.assertIn('bi-person-plus', unassigned)


class HistoryTests(TicketTestCase):
    def test_labels_set_at_creation_are_not_reported_again_by_a_later_change(self):
        ticket = self.make_ticket()
        ticket.labels.set([Label.objects.create(name='invoice')])

        ticket.size = 'days'
        ticket.save()

        lines = ' '.join(line for entry in build_feed(ticket) for line in entry.lines)
        self.assertEqual(lines.count('added label "invoice"'), 1)
        self.assertIn('set the size to Days', lines)

    def test_an_assignee_change_names_who_had_it_and_who_has_it(self):
        ticket = self.make_ticket()
        bob = get_user_model().objects.create_user(username='bob', first_name='Bob', last_name='Builder')
        for assignee in (self.user, bob, None):
            ticket.assignee = assignee
            ticket.save()

        lines = [line for entry in build_feed(ticket) for line in entry.lines]
        self.assertIn('assigned it to Anna Tester', lines)
        self.assertIn('changed the assignee from Anna Tester to Bob Builder', lines)
        self.assertIn('removed Bob Builder as assignee', lines)
        self.assertNotIn('deleted', ' '.join(lines))


class GroupSettingsTests(TicketTestCase):
    def test_a_group_s_board_opens_its_settings_and_a_tab_beside_the_groups_makes_a_new_one(self):
        settings_button = 'bi bi-gear"></i> Group settings'
        new_group = reverse('dg_board:group_create')
        new_group_tab = f'<a class="tk-tab" href="{new_group}"><i class="bi bi-plus-lg"></i> New group</a>'

        board = self.client.get('/dg/board/?group=platform')
        all_groups = self.client.get('/dg/board/?group=all')

        self.assertContains(
            board,
            f'href="{reverse("dg_board:group_edit", args=["platform"])}"><i class="{settings_button}',
        )
        self.assertContains(board, new_group_tab)
        # Across all groups there is no one group to set.
        self.assertNotContains(all_groups, settings_button)
        self.assertContains(all_groups, new_group_tab)
        created = self.client.post(reverse('dg_board:group_create'), {'name': 'Ops', 'position': 2, 'done_days': 7})
        self.assertRedirects(created, reverse('dg_board:group_edit', args=['ops']))
        self.assertEqual(Group.objects.get(slug='ops').done_days, 7)

    def test_the_board_leads_to_connecting_an_agent_when_that_is_installed(self):
        connect = reverse('dg_connect:connect')

        for group in ('platform', 'all'):
            with self.subTest(group=group):
                self.assertContains(self.client.get(f'/dg/board/?group={group}'), f'href="{connect}"')

    def test_new_is_no_group_slug_as_it_is_the_page_for_a_new_group(self):
        response = self.client.post(reverse('dg_board:group_create'), {'name': 'New', 'position': 2, 'done_days': 14})

        self.assertContains(response, 'choose another slug')
        # The error shows with the slug field, which is marked invalid.
        self.assertContains(response, 'class="form-control is-invalid" aria-invalid="true"')
        self.assertContains(response, '<div id="id_slug_error">')
        self.assertFalse(Group.objects.filter(slug='new').exists())


class GroupDeleteTests(TicketTestCase):
    def test_a_group_with_tickets_is_not_deleted(self):
        self.make_ticket()

        response = self.client.post(reverse('dg_board:group_delete', args=['platform']), follow=True)

        self.assertContains(response, 'choose a group to move them to')
        self.assertTrue(Group.objects.filter(slug='platform').exists())

    def test_the_remaining_tickets_move_to_the_matching_columns_and_the_group_goes(self):
        open_ticket, done_ticket = self.make_ticket('open'), self.make_ticket('done', column=self.done)
        wont_do = Column.objects.create(group=self.group, name="Won't do", category=Column.Category.DONE, position=3)
        skipped = self.make_ticket('skipped', column=wont_do)
        other = Group.objects.create(name='Sales', slug='sales')
        backlog = Column.objects.create(group=other, name='Backlog', category=Column.Category.TODO, position=0)
        other_done = Column.objects.create(group=other, name='Done', category=Column.Category.DONE, position=1)
        other_wont = Column.objects.create(group=other, name="Won't do", category=Column.Category.DONE, position=2)

        self.client.post(reverse('dg_board:group_delete', args=['platform']), {'move_to': other.pk})

        self.assertFalse(Group.objects.filter(slug='platform').exists())
        for ticket, column in ((open_ticket, backlog), (done_ticket, other_done), (skipped, other_wont)):
            ticket.refresh_from_db()
            self.assertEqual(ticket.column, column, ticket.title)
        self.assertIsNotNone(done_ticket.closed_at)
        lines = ' '.join(line for entry in build_feed(done_ticket) for line in entry.lines)
        self.assertIn('moved it from Platform / Done to Sales / Done', lines)

    def test_an_empty_group_goes_and_the_history_keeps_its_name(self):
        ticket = self.make_ticket()
        other = Group.objects.create(name='Sales', slug='sales')
        Column.objects.create(group=other, name='Backlog', category=Column.Category.TODO)
        self.client.post(reverse('dg_board:ticket_update', args=[ticket.pk]), {'field': 'group', 'value': other.pk})

        response = self.client.post(reverse('dg_board:group_delete', args=['platform']))

        self.assertRedirects(response, reverse('dg_board:board'))
        self.assertFalse(Group.objects.filter(slug='platform').exists())
        self.assertFalse(Column.objects.filter(pk=self.todo.pk).exists())
        lines = ' '.join(line for entry in build_feed(ticket) for line in entry.lines)
        self.assertIn('moved it from Platform / To do to Sales / Backlog', lines)
        self.assertContains(self.client.get(ticket.get_absolute_url()), 'Platform / To do')


class TicketLinkTests(TicketTestCase):
    def test_a_key_becomes_a_link_but_not_in_code_or_when_no_ticket_has_it(self):
        ticket = self.make_ticket('Linked one')

        html = render_markdown(f'See {ticket.key}, UTF-8 and `{ticket.key}`.')

        self.assertIn(f'href="{ticket.get_absolute_url()}" title="Linked one"', html)
        self.assertIn(f'>{ticket.key}</a>,', html)
        self.assertIn(f'<code>{ticket.key}</code>', html)
        self.assertNotIn('UTF-8</a>', html)

    def test_a_mention_of_a_colleague_is_marked_but_not_in_code_or_an_email_address(self):
        html = render_markdown('Ask @Anna, not @nobody. Mail anna@example.com, or see `@anna`, or @anna.')

        self.assertIn('<span class="dg-mention" title="Anna Tester">@Anna</span>,', html)
        self.assertIn('<span class="dg-mention" title="Anna Tester">@anna</span>.', html)
        self.assertEqual(html.count('dg-mention'), 2)
        self.assertIn('<code>@anna</code>', html)

    def test_no_class_but_the_mention_s_survives(self):
        html = render_markdown('<span class="text-danger dg-mention">@nobody</span>')

        self.assertNotIn('text-danger', html)


class QuickCreateTests(TicketTestCase):
    def test_a_title_typed_above_a_card_becomes_a_ticket_there(self):
        self.make_ticket('first')
        second = self.make_ticket('second')

        response = self.client.post(
            reverse('dg_board:ticket_quick_create'),
            {'column': self.todo.pk, 'title': 'squeezed in', 'before': second.pk},
        )

        created = Ticket.objects.get(title='squeezed in')
        self.assertEqual(created.creator, self.user)
        self.assertIn(created.key, response.json()['html'])
        self.assertEqual(list(self.todo.tickets.values_list('title', flat=True)), ['first', 'squeezed in', 'second'])

    def test_an_empty_title_is_refused(self):
        response = self.client.post(reverse('dg_board:ticket_quick_create'), {'column': self.todo.pk, 'title': ' '})

        self.assertEqual(response.status_code, 400)


class SearchTests(TicketTestCase):
    def test_a_key_comes_first_then_the_title_then_the_description(self):
        in_description = self.make_ticket('Unrelated', description='Mentions the invoice')
        in_title = self.make_ticket('The invoice run')
        named = self.make_ticket('Something else')

        for query, first in (
            ('invoice', in_title),
            (named.key, named),
            (str(named.pk), named),
            (named.key.lower(), named),
        ):
            with self.subTest(query=query):
                self.assertEqual(Ticket.objects.search(query).first(), first)
        self.assertEqual(list(Ticket.objects.search('invoice')), [in_title, in_description])
        self.assertFalse(Ticket.objects.search('  ').exists())

    def test_the_relation_picker_finds_a_ticket_by_its_key_number_or_title(self):
        ticket = self.make_ticket('Picked')

        for query in (str(ticket.pk), ticket.key, 'Picked'):
            with self.subTest(query=query):
                results = self.client.get(reverse('dg_board:ticket_search'), {'q': query}).json()['results']
                self.assertEqual(results[0]['key'], ticket.key)


class BoardNavigationTests(TicketTestCase):
    def test_the_assignee_filter_offers_only_people_with_a_ticket_on_the_board(self):
        here, elsewhere, idle = (
            member(username=name, first_name=name.capitalize()) for name in ('here', 'elsewhere', 'idle')
        )
        other = Group.objects.create(name='Settlers', slug='settlers')
        self.make_ticket(assignee=here)
        self.make_ticket(assignee=elsewhere, column=Column.objects.create(group=other, name='To do', position=0))
        board = reverse('dg_board:board')

        platform = self.client.get(f'{board}?group=platform').context['users']
        everywhere = self.client.get(f'{board}?group=all').context['users']
        chosen = self.client.get(f'{board}?group=platform&assignee={idle.pk}').context['users']

        self.assertEqual(list(platform), [here])
        self.assertEqual(set(everywhere), {here, elsewhere})
        self.assertIn(idle, chosen)

    def test_the_creator_filter_offers_only_people_who_created_a_ticket_on_the_board(self):
        here, elsewhere, idle = (
            member(username=name, first_name=name.capitalize()) for name in ('here', 'elsewhere', 'idle')
        )
        other = Group.objects.create(name='Settlers', slug='settlers')
        on_platform = self.make_ticket()
        on_settlers = self.make_ticket(column=Column.objects.create(group=other, name='To do', position=0))
        Ticket.objects.filter(pk=on_platform.pk).update(creator=here)
        Ticket.objects.filter(pk=on_settlers.pk).update(creator=elsewhere)
        board = reverse('dg_board:board')

        platform = self.client.get(f'{board}?group=platform').context['creator_users']
        everywhere = self.client.get(f'{board}?group=all').context['creator_users']
        chosen = self.client.get(f'{board}?group=platform&creator={idle.pk}').context['creator_users']

        self.assertEqual(list(platform), [here])
        self.assertEqual(set(everywhere), {here, elsewhere})
        self.assertIn(idle, chosen)

    def test_the_breadcrumb_goes_back_to_the_board_as_it_was_left(self):
        ticket = self.make_ticket()
        other = Group.objects.create(name='Settlers', slug='settlers')
        board = reverse('dg_board:board')

        self.client.get(f'{board}?group=platform&label=invoice')
        with_filters = self.client.get(ticket.get_absolute_url())
        self.client.get(f'{board}?group={other.slug}&label=invoice')
        from_another_group = self.client.get(ticket.get_absolute_url())

        self.assertContains(with_filters, f'href="{board}?group=platform&amp;label=invoice"')
        self.assertContains(from_another_group, f'href="{board}?group=platform"')

    def test_a_key_in_the_search_opens_the_ticket_even_when_done_long_ago(self):
        ticket = self.make_ticket('old news', column=self.done)
        Ticket.objects.filter(pk=ticket.pk).update(closed_at=ticket.closed_at - datetime.timedelta(days=400))

        response = self.client.get(
            reverse('dg_board:board'),
            {'group': 'platform', 'q': ticket.key.lower(), 'open': '1'},
        )

        self.assertRedirects(response, ticket.get_absolute_url())

    def test_a_number_alone_opens_that_ticket_and_else_searches_titles(self):
        ticket = self.make_ticket('Numbered')
        titled = self.make_ticket('Budget 99999')

        by_number = self.client.get(reverse('dg_board:board'), {'group': 'platform', 'q': str(ticket.pk), 'open': '1'})
        no_such_ticket = self.client.get(reverse('dg_board:board'), {'group': 'platform', 'q': '99999', 'open': '1'})

        self.assertRedirects(by_number, ticket.get_absolute_url())
        self.assertRedirects(no_such_ticket, titled.get_absolute_url())

    def test_a_word_with_one_match_opens_that_ticket(self):
        ticket = self.make_ticket('A unique pineapple')
        self.make_ticket('Something else')

        response = self.client.get(reverse('dg_board:board'), {'group': 'platform', 'q': 'pineapple', 'open': '1'})

        self.assertRedirects(response, ticket.get_absolute_url())

    def test_a_search_without_enter_only_filters_the_board(self):
        """Typing filters the board and puts the search in its address, which Back from the ticket loads again."""
        ticket = self.make_ticket('A unique pineapple')
        self.make_ticket('Something else')
        board = reverse('dg_board:board')

        by_word = self.client.get(board, {'group': 'platform', 'q': 'pineapple'})
        by_key = self.client.get(board, {'group': 'platform', 'q': ticket.key})

        for response in (by_word, by_key):
            self.assertEqual(response.status_code, 200)
            self.assertEqual([t for lane in response.context['lanes'] for t in lane['tickets']], [ticket])

    def test_the_board_opens_with_the_last_group_and_filters(self):
        self.client.get(reverse('dg_board:board'), {'group': 'all', 'assignee': ['me', 'none'], 'q': ''})

        response = self.client.get(reverse('dg_board:board'))

        self.assertRedirects(response, f'{reverse("dg_board:board")}?group=all&assignee=me&assignee=none')

    def test_a_search_leaves_the_remembered_view_alone(self):
        """A search from the Command Center covers all groups; the board must not reopen on them."""
        self.client.get(reverse('dg_board:board'), {'group': 'platform', 'assignee': ['me']})
        self.client.get(reverse('dg_board:board'), {'group': 'all', 'q': 'nothing matches this'})

        response = self.client.get(reverse('dg_board:board'))

        self.assertRedirects(response, f'{reverse("dg_board:board")}?group=platform&assignee=me')

    def test_a_remembered_group_that_is_gone_is_forgotten(self):
        Group.objects.create(name='Gone', slug='gone')
        self.client.get(reverse('dg_board:board'), {'group': 'gone'})
        Group.objects.filter(slug='gone').delete()

        response = self.client.get(reverse('dg_board:board'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['group'], self.group)


@mock.patch('datagroceries.core.notifications.send_notification')
class NotificationTests(TicketTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bob = member(
            username='bob',
            email='bob@example.com',
            first_name='Bob',
            last_name='Builder',
        )

    def sent(self, task):
        """Each message as the people it went to and its summary, address and quote on lines of their own."""
        return [
            (tuple(addressed(call.args[0])), '\n'.join(call.args[1][key] for key in ('summary', 'url', 'quote')))
            for call in task.enqueue.call_args_list
        ]

    def test_a_comment_tells_the_other_watchers_but_not_its_author(self, delay):
        ticket = self.make_ticket()
        Watcher.objects.create(ticket=ticket, user=self.bob)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(ticket.get_absolute_url(), {'action': 'comment', 'body': 'Looks good'})

        [(emails, message)] = self.sent(delay)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('Anna Tester commented on', message)
        self.assertIn(f'{ticket.get_absolute_url()}#comment-{Comment.objects.get().pk}\n', message)
        self.assertIn('\nLooks good', message)
        self.assertTrue(Watcher.objects.filter(ticket=ticket, user=self.user).exists())

    def test_a_mention_tells_that_person_and_makes_them_watch(self, delay):
        ticket = self.make_ticket()

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(ticket.get_absolute_url(), {'action': 'comment', 'body': 'What do you think, @bob?'})

        [(emails, message)] = self.sent(delay)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('mentioned you on', message)
        self.assertTrue(Watcher.objects.filter(ticket=ticket, user=self.bob).exists())

    def test_the_new_assignee_is_told(self, delay):
        ticket = self.make_ticket()

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('dg_board:ticket_update', args=[ticket.pk]),
                {'field': 'assignee', 'value': self.bob.pk},
            )

        [(emails, message)] = self.sent(delay)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('assigned', message)
        self.assertIn(ticket.key, message)

    def test_watchers_hear_when_a_ticket_is_done_but_not_again_within_done(self, delay):
        ticket = self.make_ticket()
        Watcher.objects.create(ticket=ticket, user=self.bob)
        wont_do = Column.objects.create(group=self.group, name="Won't do", category=Column.Category.DONE, position=3)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('dg_board:ticket_move', args=[ticket.pk]), {'column': self.done.pk})
            self.client.post(reverse('dg_board:ticket_move', args=[ticket.pk]), {'column': wont_do.pk})

        [(emails, message)] = self.sent(delay)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('to Done', message)

    def test_blocking_is_told_to_the_watchers(self, delay):
        ticket = self.make_ticket()
        Watcher.objects.create(ticket=ticket, user=self.bob)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(ticket.get_absolute_url(), {'action': 'block', 'reason': 'Waiting for Elia'})

        [(_, message)] = self.sent(delay)
        self.assertIn('blocked', message)
        self.assertIn('\nWaiting for Elia', message)

    def test_editing_a_comment_tells_only_the_people_it_newly_mentions(self, delay):
        ticket = self.make_ticket()
        Watcher.objects.create(ticket=ticket, user=self.bob)
        comment = Comment.objects.create(ticket=ticket, author=self.user, body='First')

        with self.captureOnCommitCallbacks(execute=True):
            for body in ('Second', 'Second, @bob', 'Third, @bob'):
                self.client.post(
                    ticket.get_absolute_url(),
                    {'action': 'edit_comment', 'comment': comment.pk, 'body': body},
                )

        comment.refresh_from_db()
        self.assertEqual(comment.body, 'Third, @bob')
        [(emails, message)] = self.sent(delay)
        self.assertEqual(emails, ('bob@example.com',))
        self.assertIn('mentioned you in', message)
        self.assertIn(f'#comment-{comment.pk}\n', message)
        self.assertContains(self.client.get(ticket.get_absolute_url()), '· edited')

    def test_only_its_author_edits_a_comment_and_not_to_nothing(self, delay):
        ticket = self.make_ticket()
        theirs = Comment.objects.create(ticket=ticket, author=self.bob, body='Theirs')
        mine = Comment.objects.create(ticket=ticket, author=self.user, body='Mine')

        response = self.client.post(
            ticket.get_absolute_url(),
            {'action': 'edit_comment', 'comment': theirs.pk, 'body': 'Changed'},
        )
        self.client.post(ticket.get_absolute_url(), {'action': 'edit_comment', 'comment': mine.pk, 'body': ' '})

        self.assertEqual(response.status_code, 404)
        self.assertEqual([c.body for c in Comment.objects.order_by('pk')], ['Theirs', 'Mine'])

    def test_nobody_is_told_about_their_own_change(self, delay):
        ticket = self.make_ticket()

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(ticket.get_absolute_url(), {'action': 'comment', 'body': 'Note to self'})
            self.client.post(reverse('dg_board:ticket_move', args=[ticket.pk]), {'column': self.done.pk})

        self.assertEqual(self.sent(delay), [])

    def test_watching_can_be_switched_off_and_on(self, delay):
        ticket = self.make_ticket()
        self.client.post(ticket.get_absolute_url(), {'action': 'watch'})
        self.assertTrue(ticket.watchers.filter(user=self.user).exists())

        self.client.post(ticket.get_absolute_url(), {'action': 'watch'})

        self.assertFalse(ticket.watchers.filter(user=self.user).exists())


class TimezoneTests(TicketTestCase):
    def test_times_are_in_the_zone_django_has_active(self):
        """As the project's own pages: TIME_ZONE, or each person's own, activated in a middleware."""
        ticket = self.make_ticket()

        with timezone.override('Asia/Tokyo'):
            page = self.client.get(ticket.get_absolute_url())

        self.assertContains(page, 'Hover a time for the exact time (Asia/Tokyo)')
