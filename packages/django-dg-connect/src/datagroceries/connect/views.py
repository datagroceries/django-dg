"""The "Connect an agent" page: how to connect Claude and other agents, and every connection and personal
token the person has, each revocable.

It answers every signed-in user who may use at least one area, and a 404 to anyone else.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from oauth2_provider.models import AccessToken, RefreshToken, get_application_model

from datagroceries.connect.models import ApiToken
from datagroceries.core import areas


def _scopes(user) -> list[tuple[str, str]]:
    """The areas the user may give a token, with their labels; a 404 without any."""
    scopes = [(scope, areas.AREAS[scope].label) for scope in areas.scopes_for(user)]
    if not scopes:
        raise Http404('No area is open to you.')
    return scopes


def _connections(user) -> list[dict]:
    """The apps signed in as `user` with OAuth, such as Claude, each once, with when it last signed in."""
    found = {}
    for token in RefreshToken.objects.filter(user=user, revoked=None).select_related('application'):
        app = found.setdefault(token.application_id, {'application': token.application, 'since': token.created})
        app['since'] = max(app['since'], token.created)
    return sorted(found.values(), key=lambda app: app['application'].name.lower())


@login_required
def connect(request):
    return render(
        request,
        'dg_connect/connect.html',
        {
            'scopes': _scopes(request.user),
            'mcp_url': request.build_absolute_uri(reverse('dg_core:mcp')),
            'connections': _connections(request.user),
            'tokens': ApiToken.objects.filter(user=request.user, revoked_at=None),
            'lifetimes': ApiToken.LIFETIMES.items(),
        },
    )


@login_required
@require_POST
def token_create(request):
    """Make a token for the requesting user and show its key, this once only."""
    allowed = {scope for scope, _label in _scopes(request.user)}
    name = request.POST.get('name', '').strip()[: ApiToken._meta.get_field('name').max_length]
    scopes, days = request.POST.getlist('scopes'), int(request.POST.get('days', 0))
    # Only areas the user may use now: the page offers no others, and a crafted post gets no more.
    if not name or not scopes or not set(scopes) <= allowed or days not in ApiToken.LIFETIMES:
        messages.error(request, _('Give the token a name, at least one area and a lifetime.'))
        return redirect('dg_connect:connect')
    token, key = ApiToken.issue(request.user, name, scopes, days)
    mcp_url = request.build_absolute_uri(reverse('dg_core:mcp'))
    return render(request, 'dg_connect/token_created.html', {'token': token, 'key': key, 'mcp_url': mcp_url})


@login_required
@require_POST
def token_revoke(request, token_id: int):
    token = get_object_or_404(ApiToken, id=token_id, user=request.user, revoked_at=None)
    token.revoked_at = timezone.now()
    token.save(update_fields=['revoked_at'])
    messages.success(request, _('Revoked "%(name)s". Whatever used it can no longer get in.') % {'name': token.name})
    return redirect('dg_connect:connect')


@login_required
@require_POST
def connection_revoke(request, application_id: int):
    """Disconnect an app: every token it holds for the requesting user stops at once."""
    application = get_object_or_404(get_application_model(), id=application_id)
    for token in RefreshToken.objects.filter(user=request.user, application=application, revoked=None):
        token.revoke()
    AccessToken.objects.filter(user=request.user, application=application).delete()
    messages.success(request, _('Disconnected %(name)s. It can no longer act as you.') % {'name': application.name})
    return redirect('dg_connect:connect')
