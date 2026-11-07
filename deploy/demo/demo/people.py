"""How the demo sees its people: everyone may work on every ticket, but only a superuser may change the
groups themselves, so no visitor rearranges or deletes the board for the others before the night's reset."""

from datagroceries.core.people import People


class DemoPeople(People):
    def may(self, user, right, group):
        return right != 'manage' or user.is_superuser
