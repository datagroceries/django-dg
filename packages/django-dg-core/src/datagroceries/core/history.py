"""Who made a change, for django-simple-history, without its middleware: the DataGroceries views say which
request they serve, so the project need not add `HistoryRequestMiddleware`. Where it has, that comes
first and this does nothing."""

import contextlib

from simple_history.models import HistoricalRecords


@contextlib.contextmanager
def recording(request):
    """While open, changes are recorded as made by `request.user`, and through its token (request.auth)."""
    if getattr(HistoricalRecords.context, 'request', None) is not None:
        yield
        return
    HistoricalRecords.context.request = request
    try:
        yield
    finally:
        del HistoricalRecords.context.request


def current_request():
    """The request a DataGroceries view or API call is serving, or None outside one, such as in a task."""
    return getattr(HistoricalRecords.context, 'request', None)
