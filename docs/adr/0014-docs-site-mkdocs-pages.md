# ADR 0014: Docs site on MkDocs with GitHub Pages

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** n/a

## Context

The project ships a lot of long-form documentation: ADRs, STPA
artefacts, conformance posture, model cards, hardware profiles. A
docs site lets a reader navigate them without `git clone`. Sphinx is
heavier than needed; raw markdown on the GitHub web view does not
render mermaid diagrams.

## Decision

The docs site is MkDocs (Material theme) built with `mkdocs build
--strict`. Mermaid diagrams render via `mkdocs-mermaid2-plugin`. Python
docstrings render via `mkdocstrings[python]`. The site builds in CI
(`.github/workflows/docs.yml`) and deploys to GitHub Pages on push to
`main` and on tag pushes.

The `docs/` tree is the source. `scripts/gen_*.py` regenerate the tool
reference, the ADR index, and the backlog summary so the site stays
in sync with code.

## Consequences

Easier: readers land on a navigable site; mermaid diagrams render; the
strict build catches dead links.

Harder: a markdown file outside the `nav` causes a strict-build
failure. The maintainer must keep `mkdocs.yml` in sync.

## Revisit triggers

- The site grows beyond what GitHub Pages can serve.
- A second docs target (e.g. a PDF safety case) becomes a requirement.
