# Releasing

Publishing is automated by `.github/workflows/publish.yml` and uses PyPI
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — an OIDC token
minted per run, so no API token is stored in this repository.

## Setup

Already done, and confirmed working by the 0.1.0 release: the `pypi`
environment exists on the repository and PyPI has a matching trusted publisher.
Nothing needs configuring to cut a release.

For the record, and in case it ever has to be rebuilt, the publisher on PyPI is
registered under *Your projects → Publishing* as:

| Field | Value |
| --- | --- |
| Owner | `openhistorymap` |
| Repository name | `yesterdays-panoramax` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Adding required reviewers to the `pypi` environment under **Settings →
Environments** is worth considering, since a version cannot be reused once it
is taken.

## Cutting a release

1. Bump `version` in `pyproject.toml`.
2. Move the unreleased entries in `CHANGELOG.md` under the new version, dated.
3. Merge to `main`; confirm CI is green.
4. Publish a GitHub Release with tag `v<version>` — for example `v0.2.0`.

The workflow builds an sdist and a wheel, runs `twine check --strict`, and
**refuses to continue if the tag and `pyproject.toml` disagree** (a mismatch
means the tag, the changelog and the artefact would all disagree, and PyPI will
not let a version be reused once taken).

## If a publish fails

Re-run the failed run rather than tagging again:

```
gh run rerun <run-id> --failed
```

It replays as the same release event, so the tag-vs-version check still applies
and the version number is not consumed by the failed attempt — PyPI only
records a version once a file has actually been uploaded.

A GitHub Release is the workflow's only trigger, on purpose. A manual dispatch
would publish whatever version happened to be in `pyproject.toml` on whatever
branch it ran from, and would bypass the tag check, which has no tag to compare
against outside a release. That mistake cannot be undone.

## Versioning

Semantic versioning, with one project-specific rule: **any change to the
identifier scheme is a major version.** Published UUIDs are a function of
`PANORAMAX_UUID_NAMESPACE` and the primary key, so a change to how they are
derived silently orphans everything the federation has already harvested.
