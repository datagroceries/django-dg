"""Tests for the board in another language: the pages follow the project's, the API stays English."""

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from gilde.board.models import Relation, Ticket
from gilde.board.tests.test_tickets import TicketTestCase
from gilde.core.tests import TEST_AUTHENTICATION, issue


@override_settings(LANGUAGE_CODE='nl')
class DutchTests(TicketTestCase):
    def test_the_board_speaks_dutch(self):
        self.make_ticket('Factuur')

        page = self.client.get(reverse('gilde_board:board'))

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
        catalog = self.client.get(reverse('gilde_core:javascript_catalog'))

        self.assertContains(catalog, 'Opslaan\\u2026')

    @override_settings(GILDE_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
    def test_the_api_stays_english_for_agents(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {issue(self.user)}')

        refused = client.post('/gilde/board/api/tickets/', {'title': 'Nergens', 'parent': 'EX-99999'}, format='json')

        self.assertEqual(refused.status_code, 400)
        self.assertNotIn('bestaat', refused.content.decode())
