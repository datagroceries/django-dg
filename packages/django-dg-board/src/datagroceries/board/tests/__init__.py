from datagroceries.core.tests import person


def member(**fields):
    """Someone who may use the board."""
    return person('dg_board.use', **fields)
