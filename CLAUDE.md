# DataGroceries: instructions for agents

- Code, comments, docs and commit messages are in English. Texts people see are marked for translation,
  and the Dutch `.po` files are updated with them.
- What gets in, the layout and the conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); read it before a
  change of any size. How the board and the wiki are built is in [docs/board.md](docs/board.md) and
  [docs/wiki.md](docs/wiki.md), the decisions and why in
  [docs/decisions.md](docs/decisions.md), and the integration guide in [docs/integrating.md](docs/integrating.md).
- A page and an MCP tool do the same thing through the same code; change both together.

## Commands

Run from the repository root, in the virtualenv `.venv` (CONTRIBUTING.md says how to make it):

```bash
.venv/bin/pytest -q                                  # all tests
.venv/bin/ruff check --fix <files> && .venv/bin/ruff format <files>
.venv/bin/python example/manage.py <command>         # the example project
```
