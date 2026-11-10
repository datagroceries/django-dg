"""Whether every compiled translation (.mo) in git says what its .po says, for CI: each .po is compiled
afresh with msgfmt, as `compilemessages` does, and the two catalogs compared by their messages, not their
bytes, which differ between versions of gettext."""

import gettext
import pathlib
import subprocess
import sys
import tempfile


def catalog(path) -> dict:
    """The messages and their translations, without the header, whose dates change on every makemessages."""
    with pathlib.Path(path).open('rb') as file:
        return {message: text for message, text in gettext.GNUTranslations(file)._catalog.items() if message}


stale = []
for po in sorted(pathlib.Path('packages').glob('*/src/datagroceries/*/locale/*/LC_MESSAGES/*.po')):
    mo = po.with_suffix('.mo')
    with tempfile.TemporaryDirectory() as folder:
        fresh = pathlib.Path(folder) / mo.name
        subprocess.run(['msgfmt', '--check-format', '-o', fresh, po], check=True)  # noqa: S603, S607 - gettext's own
        if not mo.exists() or catalog(mo) != catalog(fresh):
            stale.append(po)

for po in stale:
    sys.stdout.write(f'{po.with_suffix(".mo")} is not what {po} says: run compilemessages in its app.\n')
sys.exit(1 if stale else 0)
