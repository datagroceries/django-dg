"""The MCP endpoint of the DataGroceries apps: one server for every installed app, so an agent needs one connection.

A tools-only MCP server over Streamable HTTP, stateless: every JSON-RPC message is one POST answered
with one JSON response, so it runs on any WSGI server. It answers initialize, ping, tools/list and
tools/call, and takes notifications without a reply.

The caller logs in any way datagroceries.core.authentication lets in, such as a personal token or the Claude
connector's OAuth (django-dg-connect), or a way of the host project's own, and every tool acts as
them. A tool is a REST view of an app's own API, run
in-process with the tool's arguments as its path, query or body: the rules, the validation and the
answers are the REST API's, and an error it answers comes back as a failed tool call with the same JSON.
A tool is listed and runs only while its area is open to the caller.
"""

import dataclasses

from django.http import Http404, QueryDict
from django.utils.datastructures import MultiValueDict
from rest_framework import status
from rest_framework.exceptions import APIException, ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from datagroceries.core import areas
from datagroceries.core.authentication import DataGroceriesAuthentication, opens

# The protocol versions we speak, newest first; a client asking for another gets the newest.
PROTOCOL_VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26')
INSTRUCTIONS = (
    'Tools acting as the person who connected them: they reach what that person may reach, whatever they '
    "change is done in that person's name, and the history says it went through this connection."
)


class _ToolRequest(Request):
    """The MCP request as a REST view sees it: the same user and token, with the tool's arguments as the
    body or the query."""

    def __init__(self, request: Request, body: dict, query: QueryDict):
        super().__init__(request._request)
        self._full_data = self._data = body
        self._files = MultiValueDict()
        self._query = query
        self._user, self._auth = request.user, request.auth

    @property
    def query_params(self):
        return self._query


def _query(arguments: dict) -> QueryDict:
    """Arguments as query parameters: a list as a repeated parameter, a boolean as true or false."""
    query = QueryDict(mutable=True)
    for name, value in arguments.items():
        values = value if isinstance(value, list) else [value]
        query.setlist(name, [str(item).lower() if isinstance(item, bool) else str(item) for item in values])
    return query


@dataclasses.dataclass(frozen=True)
class Tool:
    """One MCP tool: a REST view and method, with the JSON schema of its arguments. The arguments named
    in `path` go into the URL; the others are the query of a GET, or else the body. `destructive` marks
    a tool that undoes something, so that the agent asks before calling it."""

    name: str
    title: str
    description: str
    view: type[APIView]
    method: str
    properties: dict
    required: tuple = ()
    path: tuple = ()
    destructive: bool = False

    def definition(self) -> dict:
        return {
            'name': self.name,
            'title': self.title,
            'description': self.description,
            'inputSchema': {
                'type': 'object',
                'properties': self.properties,
                'required': [*self.path, *self.required],
                'additionalProperties': False,
            },
            'annotations': {
                'readOnlyHint': self.method == 'GET',
                'destructiveHint': self.destructive,
                'openWorldHint': False,
            },
        }

    def run(self, request: Request, arguments: dict) -> Response:
        """The view's answer to these arguments, errors included, as the REST API would give it."""
        missing = [name for name in (*self.required, *self.path) if name not in arguments]
        if missing:
            return Response({'missing_arguments': missing}, status=status.HTTP_400_BAD_REQUEST)
        kwargs = {name: arguments[name] for name in self.path}
        rest = {name: value for name, value in arguments.items() if name not in self.path}
        if self.method == 'GET':
            inner = _ToolRequest(request, {}, _query(rest))
        else:
            inner = _ToolRequest(request, rest, QueryDict())
        handler = self.method.lower()
        view = self.view(request=inner, args=(), kwargs=kwargs, format_kwarg=None)
        try:
            return getattr(view, handler)(inner, **kwargs)
        except (APIException, Http404) as error:
            # What the REST API answers for it: a 400 with the fields, a 404, and so on.
            return view.handle_exception(error)

    def call(self, request: Request, arguments: dict) -> dict:
        """The MCP result of tools/call: the view's JSON as text, failed if it answered an error."""
        response = self.run(request, arguments)
        text = JSONRenderer().render(response.data).decode()
        return {
            'content': [{'type': 'text', 'text': text}],
            'isError': response.status_code >= status.HTTP_400_BAD_REQUEST,
        }


def _open_tools(request) -> dict[str, Tool]:
    return {tool.name: tool for scope, area in areas.AREAS.items() if opens(request, scope) for tool in area.tools}


def _result(message_id, result: dict) -> Response:
    return Response({'jsonrpc': '2.0', 'id': message_id, 'result': result})


def _error(message_id, code: int, message: str) -> Response:
    return Response({'jsonrpc': '2.0', 'id': message_id, 'error': {'code': code, 'message': message}})


class McpView(DataGroceriesAuthentication, APIView):
    """The MCP endpoint: one JSON-RPC message per POST. There is no event stream to GET."""

    permission_classes = (IsAuthenticated,)
    renderer_classes = (JSONRenderer,)

    def post(self, request):
        try:
            message = request.data
        except ParseError:
            return _error(None, -32700, 'Parse error')
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or 'method' not in message:
            return _error(message.get('id') if isinstance(message, dict) else None, -32600, 'Invalid request')
        if 'id' not in message:
            # A notification, such as notifications/initialized: nothing to answer.
            return Response(status=status.HTTP_202_ACCEPTED)
        message_id, params = message['id'], message.get('params') or {}
        match message['method']:
            case 'initialize':
                asked = params.get('protocolVersion')
                open_areas = [area for scope, area in areas.AREAS.items() if opens(request, scope)]
                return _result(
                    message_id,
                    {
                        'protocolVersion': asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                        'capabilities': {'tools': {'listChanged': False}},
                        'serverInfo': {'name': 'datagroceries', 'title': 'DataGroceries', 'version': '1'},
                        'instructions': ' '.join([INSTRUCTIONS, *(area.instructions for area in open_areas)]),
                    },
                )
            case 'ping':
                return _result(message_id, {})
            case 'tools/list':
                return _result(message_id, {'tools': [tool.definition() for tool in _open_tools(request).values()]})
            case 'tools/call':
                tool = _open_tools(request).get(params.get('name'))
                if tool is None:
                    return _error(message_id, -32602, f'Unknown tool: {params.get("name")}')
                return _result(message_id, tool.call(request, params.get('arguments') or {}))
            case _:
                return _error(message_id, -32601, f'Method not found: {message["method"]}')
