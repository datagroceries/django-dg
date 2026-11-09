import contextlib

from django.test import RequestFactory

from datagroceries.core import history
from datagroceries.core.tests import person


def page(title, creator, parent=None, **fields):
    """A page; its parent made a folder first, as only a folder has pages in it."""
    from datagroceries.wiki.models import Page  # noqa: PLC0415 - models need the apps loaded

    if parent is not None and not parent.folder:
        parent.folder = True
        Page.objects.filter(pk=parent.pk).update(folder=True)
    return Page.objects.create(title=title, parent=parent, creator=creator, **fields)


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
