# Releasing

Each package is released on its own, from GitHub Actions ([release.yml](../.github/workflows/release.yml)),
through PyPI's trusted publishing: no PyPI token is stored anywhere.

## Once, per package

On PyPI, under the account that will own the packages: *Your projects › Publishing › Add a new pending
publisher*, for each of `django-dg-core`, `django-dg-connect`, `django-dg-board` and
`django-dg-wiki`:

| Field | Value |
|---|---|
| Owner | `datagroceries` |
| Repository | `django-dg` |
| Workflow | `release.yml` |
| Environment | `pypi` |

On GitHub, in the repository's settings, an environment `pypi`, with Jasper as required reviewer, so
nothing is published without a click.

## Each release

1. Set the version in the package's `pyproject.toml`, and a section for it at the top of its
   `CHANGELOG.md`, with the date. Core first when an app needs a new core: an app's dependency on
   `django-dg-core` names the lowest version it works with.
2. Commit, push, and wait for CI to pass.
3. Tag and push the tag, for example:

   ```bash
   git tag django-dg-board-v1.0.0 && git push origin django-dg-board-v1.0.0
   ```

4. Approve the `pypi` environment in the run on GitHub. The workflow runs every test again, builds the
   package, checks it with `twine check`, and publishes it.

Versions follow semantic versioning: a major version for a change a project must act on, such as a
setting or a URL that changes; a minor one for something new; a patch for a fix.
