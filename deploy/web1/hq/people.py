"""Who may do what on hq. Jasper and whoever else may use the board, the team, may do everything. Everyone
else reads the wiki's public folders: without an account, and with one, made in a minute (accounts.py),
they comment there too. Nothing else of the board or the wiki shows to them."""

from django.contrib.auth import get_user_model

from datagroceries.core.people import People, includes
from datagroceries.wiki.models import TOP, Page

# The wiki's public folders, by their address: renamed or moved, a folder stops being public, which is the
# safe way round.
PUBLIC = {'board', 'wiki'}


class HqPeople(People):
    def may_use(self, user, area):
        if not user.is_authenticated:
            return area.scope == 'wiki'
        return super().may_use(user, area)

    def members(self, area):
        """The team, in the wiki too: a reader can be neither assigned nor mentioned, so nobody who signs up
        sees who else did. Readers hear about the pages they watch."""
        users = get_user_model()._default_manager.with_perm(
            'dg_board.use', is_active=True, backend='django.contrib.auth.backends.ModelBackend'
        )
        return users.order_by(*self.ordering())

    def may(self, user, right, where):
        if user.is_authenticated and user.has_perm('dg_board.use'):
            return True
        if where is TOP:
            return right == 'read'
        if not isinstance(where, Page) or where.path.split('/')[0] not in PUBLIC:
            return False
        return includes('comment', right)
