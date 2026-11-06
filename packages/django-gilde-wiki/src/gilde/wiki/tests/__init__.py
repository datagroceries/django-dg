from gilde.core.tests import person


def member(**fields):
    """Someone who may use the wiki."""
    return person('gilde_wiki.use', **fields)
