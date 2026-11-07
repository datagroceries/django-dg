from datagroceries.core.tests import person


def member(**fields):
    """Someone who may use the wiki."""
    return person('dg_wiki.use', **fields)
