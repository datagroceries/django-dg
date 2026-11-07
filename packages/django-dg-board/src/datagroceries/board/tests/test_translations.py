"""Tests for the board in another language: the pages follow the project's, the API stays English, and
notifications are in the project's language whatever the page or the API was in."""

from unittest import mock

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from datagroceries.board.models import Relation, Ticket, Watcher
from datagroceries.board.tests import member
from datagroceries.board.tests.test_tickets import TicketTestCase
from datagroceries.core.people import People
from datagroceries.core.tests import TEST_AUTHENTICATION, addressed, issue


class DutchBob(People):
    """A project that knows Bob reads Dutch."""

    def language(self, user):
        return 'nl' if user.username == 'bob' else None


@override_settings(LANGUAGE_CODE='nl')
class DutchTests(TicketTestCase):
    def test_the_board_speaks_dutch(self):
        self.make_ticket('Factuur')

        page = self.client.get(reverse('dg_board:board'))

        self.assertContains(page, '<html lang="nl"')
        self.assertContains(page, 'Alle groepen')
        self.assertContains(page, 'Nieuw ticket in')
        self.assertContains(page, 'placeholder="Titel of nummer  ( / )"')

    def test_the_ticket_page_and_its_history_speak_dutch(self):
        ticket = self.make_ticket('Factuur')
        other = self.make_ticket('Betaling')
        Relation.objects.create(source=ticket, target=other, type=Relation.Type.BLOCKS)
        Ticket.objects.filter(pk=ticket.pk).update(size=Ticket.Size.DAYS)
        self.client.post(ticket.get_absolute_url(), {'action': 'block', 'reason': 'Wacht op de bank'})

        page = self.client.get(ticket.get_absolute_url())

        self.assertContains(page, 'Activiteit')
        self.assertContains(page, 'maakte het ticket aan')
        self.assertContains(page, f'voegde &quot;blokkeert {other.key}&quot; toe')
        self.assertContains(page, '<option value="blocked_by">geblokkeerd door</option>')
        self.assertContains(page, 'blokkeerde het ticket')
        self.assertContains(page, 'Dagen')

    def test_the_javascript_texts_speak_dutch(self):
        catalog = self.client.get(reverse('dg_core:javascript_catalog'))

        self.assertContains(catalog, 'Opslaan\\u2026')

    @override_settings(DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
    def test_the_api_stays_english_for_agents(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.user)}')

        refused = client.post('/dg/board/api/tickets/', {'title': 'Nergens', 'parent': 'EX-99999'}, format='json')

        self.assertEqual(refused.status_code, 400)
        self.assertNotIn('bestaat', refused.content.decode())


@mock.patch('datagroceries.core.notifications.send_notification')
class NotificationLanguageTests(TicketTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bob = member(username='bob', email='bob@example.com', first_name='Bob', last_name='Builder')

    def summary(self, task) -> str:
        [call] = task.enqueue.call_args_list
        return call.args[1]['summary']

    def summaries(self, task) -> dict:
        """Each message's summary, by who it went to."""
        return {tuple(addressed(call.args[0])): call.args[1]['summary'] for call in task.enqueue.call_args_list}

    @override_settings(LANGUAGE_CODE='nl', DG_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
    def test_in_the_project_s_language_even_from_the_english_api(self, task):
        ticket = self.make_ticket('Factuur')
        Watcher.objects.create(ticket=ticket, user=self.bob)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.user)}')

        with self.captureOnCommitCallbacks(execute=True):
            client.post(f'/dg/board/api/tickets/{ticket.key}/comments/', {'body': 'Klaar'}, format='json')

        self.assertEqual(self.summary(task), f'Anna Tester reageerde op {ticket}')

    def test_not_in_the_language_of_the_page_it_was_made_on(self, task):
        ticket = self.make_ticket('Invoice')
        Watcher.objects.create(ticket=ticket, user=self.bob)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                ticket.get_absolute_url(), {'action': 'block', 'reason': 'Waiting'}, HTTP_ACCEPT_LANGUAGE='nl'
            )

        self.assertEqual(self.summary(task), f'Anna Tester blocked {ticket}')

    @override_settings(DG_PEOPLE='datagroceries.board.tests.test_translations.DutchBob')
    def test_each_person_in_the_language_the_project_says(self, task):
        ticket = self.make_ticket('Invoice')
        carol = member(username='carol', email='carol@example.com', first_name='Carol', last_name='Singer')
        Watcher.objects.create(ticket=ticket, user=self.bob)
        Watcher.objects.create(ticket=ticket, user=carol)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(ticket.get_absolute_url(), {'action': 'comment', 'body': 'Done'})

        self.assertEqual(
            self.summaries(task),
            {
                ('bob@example.com',): f'Anna Tester reageerde op {ticket}',
                ('carol@example.com',): f'Anna Tester commented on {ticket}',
            },
        )
