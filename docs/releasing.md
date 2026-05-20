# Releasing

`nous` follows semver. Releases are tags on `main` of the form `vX.Y.Z`.

## Release checklist

1. `git checkout main && git pull`.
2. `make check && make docs-build` must be green.
3. Move all `[Unreleased]` entries in `CHANGELOG.md` into a new
   `[vX.Y.Z] - YYYY-MM-DD` heading and leave a fresh `[Unreleased]`
   block above.
4. Bump `version` in `pyproject.toml` and `__version__` in
   `src/nous/__init__.py`.
5. Commit (`chore(release): vX.Y.Z`), sign off (`-s`).
6. Tag (`git tag -s vX.Y.Z -m "vX.Y.Z"`).
7. Push (`git push --follow-tags`).
8. The docs workflow deploys the site for the new tag.

## Backporting

Pre-1.0, only `main` receives fixes. A security fix that needs to land
on a stale tag is cut as a new tag from `main` rather than as a branch
backport.

## Yanking

A bad release is yanked by tagging a `vX.Y.Z+yank.N` and updating the
release notes to point at the replacement.
