from gilde.core.tests import person


def member(**fields):
    """Someone who may use the board."""
    return person('gilde_board.use', **fields)
