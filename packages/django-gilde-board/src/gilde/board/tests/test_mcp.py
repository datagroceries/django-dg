"""Tests for the board's tools on the MCP endpoint (gilde.core.mcp, gilde.board.mcp): the protocol, which
tools a person gets, and the tools answering as the REST API does."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from gilde.board.models import Ticket
from gilde.board.tests import member
from gilde.board.tests.test_api import TicketApiTestCase
from gilde.core.tests import TEST_AUTHENTICATION, issue

URL = '/gilde/mcp/'
TICKET_TOOLS = {
    'list_ticket_groups',
    'search_tickets',
    'get_ticket',
    'create_ticket',
    'update_ticket',
    'comment_on_ticket',
    'edit_comment',
    'relate_tickets',
    'unrelate_tickets',
    'set_ticket_blocked',
    'watch_ticket',
    'unwatch_ticket',
}


def token_client(user, scopes=('board',), name='Claude Code') -> APIClient:
    key = issue(user, name, scopes)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {key}')
    return client


def call(client, method, params=None, message_id=1):
    """Send one JSON-RPC message; the HTTP response."""
    message = {'jsonrpc': '2.0', 'method': method, **({'id': message_id} if message_id is not None else {})}
    if params is not None:
        message['params'] = params
    return client.post(URL, json.dumps(message), content_type='application/json')


def tool(client, name, **arguments) -> tuple[dict, bool]:
    """Call a tool; what it answered, and whether that was an error."""
    result = call(client, 'tools/call', {'name': name, 'arguments': arguments}).json()['result']
    return json.loads(result['content'][0]['text']), result['isError']


@override_settings(GILDE_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
class ProtocolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = member(username='anna', email='anna@example.com')

    def setUp(self):
        self.client = token_client(self.user)

    def test_without_a_token_nothing_answers(self):
        response = call(APIClient(), 'initialize', {'protocolVersion': '2025-06-18'})

        self.assertEqual(response.status_code, 401)
        self.assertTrue(response['WWW-Authenticate'].startswith('Bearer'))

    def test_initialize_agrees_on_a_protocol_version(self):
        known = call(self.client, 'initialize', {'protocolVersion': '2025-06-18'}).json()['result']
        unknown = call(self.client, 'initialize', {'protocolVersion': '2030-01-01'}).json()['result']

        self.assertEqual(known['protocolVersion'], '2025-06-18')
        self.assertEqual(unknown['protocolVersion'], '2025-11-25')
        self.assertEqual(known['capabilities'], {'tools': {'listChanged': False}})

    def test_the_instructions_are_those_of_the_open_areas(self):
        opened = call(self.client, 'initialize', {'protocolVersion': '2025-06-18'}).json()['result']
        closed = call(token_client(self.user, scopes=()), 'initialize', {'protocolVersion': '2025-06-18'})

        self.assertIn('The board is the ticket tracker', opened['instructions'])
        self.assertNotIn('The board is the ticket tracker', closed.json()['result']['instructions'])

    def test_the_examples_use_the_board_s_own_keys(self):
        opened = call(self.client, 'initialize', {'protocolVersion': '2025-06-18'}).json()['result']
        tools = {tool['name']: tool for tool in call(self.client, 'tools/list').json()['result']['tools']}

        self.assertIn('its key (EX-123)', opened['instructions'])
        self.assertEqual(
            tools['get_ticket']['inputSchema']['properties']['key']['description'], 'The ticket key, e.g. EX-123.'
        )

    def test_a_notification_gets_no_answer(self):
        response = call(self.client, 'notifications/initialized', message_id=None)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b'')

    def test_ping_and_unknown_methods(self):
        self.assertEqual(call(self.client, 'ping').json(), {'jsonrpc': '2.0', 'id': 1, 'result': {}})
        self.assertEqual(call(self.client, 'resources/list').json()['error']['code'], -32601)

    def test_the_address_works_without_the_trailing_slash(self):
        """Some clients drop the slash; a redirect to the slashed address would lose the POST and its login."""
        message = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        response = self.client.post(URL.rstrip('/'), message, content_type='application/json')

        self.assertEqual(response.json()['result'], {})

    def test_there_is_no_event_stream(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_a_deactivated_person_s_token_stops_at_once(self):
        self.user.is_active = False
        self.user.save()

        self.assertEqual(call(self.client, 'tools/list').status_code, 401)


@override_settings(GILDE_AUTHENTICATION_CLASSES=TEST_AUTHENTICATION)
class ToolListTests(TestCase):
    """A tool is there only while its area is open to the caller, as a REST endpoint would be."""

    def test_staff_get_the_board_s_tools(self):
        user = member(username='anna', email='anna@example.com')

        tools = {tool['name']: tool for tool in call(token_client(user), 'tools/list').json()['result']['tools']}

        self.assertEqual(set(tools), TICKET_TOOLS)
        self.assertEqual(tools['get_ticket']['inputSchema']['required'], ['key'])
        self.assertTrue(tools['get_ticket']['annotations']['readOnlyHint'])
        self.assertTrue(tools['unrelate_tickets']['annotations']['destructiveHint'])

    def test_someone_who_left_staff_loses_the_tools(self):
        user = get_user_model().objects.create_user(username='oud', email='oud@example.com')
        client = token_client(user)

        self.assertEqual(call(client, 'tools/list').json()['result']['tools'], [])
        self.assertEqual(
            call(client, 'tools/call', {'name': 'get_ticket', 'arguments': {}}).json()['error']['code'],
            -32602,
        )

    def test_a_token_without_the_board_gets_none_of_its_tools(self):
        user = member(username='anna', email='anna@example.com')

        self.assertEqual(call(token_client(user, scopes=()), 'tools/list').json()['result']['tools'], [])


class TicketToolTests(TicketApiTestCase):
    """The ticket tools are the ticket API: TicketApiTestCase's board, reached through MCP."""

    def setUp(self):
        super().setUp()
        self.claude = token_client(self.user, name='Claude')

    def test_search_takes_lists_and_booleans(self):
        mine = self.make_ticket('Mine', assignee=self.user)
        self.make_ticket('Blocked and mine', assignee=self.user, is_blocked=True)
        self.make_ticket("Bob's", assignee=self.bob)

        found, error = tool(self.claude, 'search_tickets', assignee=['me'], blocked=False)

        self.assertFalse(error)
        self.assertEqual([ticket['key'] for ticket in found['results']], [mine.key])

    def test_get_ticket_answers_as_the_rest_api(self):
        ticket = self.make_ticket('Invoices', description='Send them.')

        found, error = tool(self.claude, 'get_ticket', key=ticket.key)

        self.assertFalse(error)
        self.assertEqual(found, self.get(f'{ticket.key}/').json())

    def test_a_missing_ticket_is_a_failed_call(self):
        answer, error = tool(self.claude, 'get_ticket', key='EX-999999')

        self.assertTrue(error)
        self.assertEqual(answer, {'detail': 'No ticket EX-999999.'})

    def test_create_records_the_connection_in_the_history(self):
        made, error = tool(self.claude, 'create_ticket', title='From Claude', group='platform')

        self.assertFalse(error)
        ticket = Ticket.objects.get(title='From Claude')
        self.assertEqual(made['key'], ticket.key)
        self.assertEqual(ticket.creator, self.user)
        self.assertEqual(ticket.history.earliest().history_change_reason, 'via Claude')

    def test_a_comment_is_edited_by_its_id_in_the_url(self):
        ticket = self.make_ticket()
        posted, _ = tool(self.claude, 'comment_on_ticket', key=ticket.key, body='Frist draft')

        edited, error = tool(self.claude, 'edit_comment', key=ticket.key, comment_id=posted['id'], body='First draft')

        self.assertFalse(error)
        self.assertEqual(edited['body'], 'First draft')
        self.assertEqual(ticket.comments.get().body, 'First draft')

    def test_arguments_are_checked_as_the_rest_api_checks_its_body(self):
        ticket = self.make_ticket()

        unknown, unknown_error = tool(self.claude, 'update_ticket', key=ticket.key, colour='red')
        missing, missing_error = tool(self.claude, 'comment_on_ticket', body='No key')

        self.assertTrue(unknown_error)
        self.assertEqual(unknown, {'unknown_fields': ['colour']})
        self.assertTrue(missing_error)
        self.assertEqual(missing, {'missing_arguments': ['key']})

    def test_update_block_and_watch(self):
        ticket = self.make_ticket()

        tool(self.claude, 'update_ticket', key=ticket.key, column='Doing', assignee='bob@example.com')
        tool(self.claude, 'set_ticket_blocked', key=ticket.key, blocked=True, reason='Waiting for a supplier')
        watched, _error = tool(self.claude, 'unwatch_ticket', key=ticket.key)

        ticket.refresh_from_db()
        self.assertEqual((ticket.column, ticket.assignee, ticket.is_blocked), (self.doing, self.bob, True))
        self.assertNotIn(self.user.email, [watcher['email'] for watcher in watched['watchers']])
