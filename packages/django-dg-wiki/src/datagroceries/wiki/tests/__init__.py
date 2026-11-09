import contextlib

from django.test import RequestFactory

from datagroceries.core import history
from datagroceries.core.tests import person


def member(**fields):
    """Someone who may use the wiki."""
    return person('dg_wiki.use', **fields)


@contextlib.contextmanager
def serving(user):
    """As while a page is served to `user`: what they may see of the wiki is what shows."""
    request = RequestFactory().get('/')
    request.user = user
    with history.recording(request):
        yield
