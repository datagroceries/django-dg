"""The demo's own pages: the welcome page, and an account of one's own with one click."""

import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group as UserGroup
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from demo import seed

# Accounts a day, so a script cannot fill the server; the reset empties them every night.
MAX_VISITORS = 1000


def _next(request) -> str:
    """Where to go after the account is made: back to what sent the visitor here, such as Claude's
    sign-in, else the board."""
    wanted = request.POST.get('next') or request.GET.get('next') or ''
    if url_has_allowed_host_and_scheme(wanted, {request.get_host()}, require_https=request.is_secure()):
        return wanted
    return reverse('gilde_board:board')


def welcome(request):
    return render(
        request,
        'demo/welcome.html',
        {'next': _next(request), 'mcp_url': request.build_absolute_uri(reverse('gilde_core:mcp'))},
    )


@require_POST
def try_it(request):
    if not request.user.is_authenticated:
        members = UserGroup.objects.get(name=seed.MEMBERS)
        if members.user_set.count() >= MAX_VISITORS + len(seed.TEAM):
            messages.error(request, _('The demo is full for today. It starts again tomorrow morning.'))
            return redirect('welcome')
        with transaction.atomic():
            visitor = _new_visitor()
            members.user_set.add(visitor)
            seed.welcome(visitor)
        login(request, visitor, backend='django.contrib.auth.backends.ModelBackend')
    return redirect(_next(request))


def _new_visitor():
    """An account without a password or an email address, named by a number: "Visitor 4821"."""
    users = get_user_model().objects
    while True:
        number = 1000 + secrets.randbelow(9000)
        if not users.filter(username=f'visitor-{number}').exists():
            return users.create_user(f'visitor-{number}', first_name='Visitor', last_name=str(number))
