# Releasing

Publishing is automated by `.github/workflows/publish.yml` and uses PyPI
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — an OIDC token
minted per run, so no API token is stored in this repository.

## One-time setup

The GitHub half is already done: the `pypi` and `testpypi` environments exist
on the repository. Adding required reviewers to `pypi` under **Settings →
Environments** is worth considering, since a version cannot be reused once it
is taken.

The PyPI half needs an account login and cannot be automated. Because the
project does not exist on either index yet, what you create is a **pending
publisher** — on PyPI under *Your projects → Publishing*, and again on
TestPyPI:

| Field | PyPI | TestPyPI |
| --- | --- | --- |
| PyPI project name | `yesterdays-panoramax` | `yesterdays-panoramax` |
| Owner | `openhistorymap` | `openhistorymap` |
| Repository name | `yesterdays-panoramax` | `yesterdays-panoramax` |
| Workflow name | `publish.yml` | `publish.yml` |
| Environment name | `pypi` | `testpypi` |

These are not guesses. A dry run against TestPyPI on 2026-08-31 produced a
valid OIDC token whose claims were `repository: openhistorymap/yesterdays-panoramax`,
`workflow_ref: .../.github/workflows/publish.yml@refs/heads/main`,
`environment: testpypi` — and failed only with `invalid-publisher`, meaning
PyPI had nothing registered to match. Everything upstream of the handshake
(build, `twine check --strict`, artefact hand-off) already works.

## Cutting a release

1. Bump `version` in `pyproject.toml`.
2. Move the unreleased entries in `CHANGELOG.md` under the new version, dated.
3. Merge to `main`; confirm CI is green.
4. Publish a GitHub Release with tag `v<version>` — for example `v0.2.0`.

The workflow builds an sdist and a wheel, runs `twine check --strict`, and
**refuses to continue if the tag and `pyproject.toml` disagree** (a mismatch
means the tag, the changelog and the artefact would all disagree, and PyPI will
not let a version be reused once taken).

## Dry run

To rehearse against TestPyPI without tagging, run the **Publish** workflow
manually with `target: testpypi`, then:

```
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            yesterdays-panoramax
```

## Versioning

Semantic versioning, with one project-specific rule: **any change to the
identifier scheme is a major version.** Published UUIDs are a function of
`PANORAMAX_UUID_NAMESPACE` and the primary key, so a change to how they are
derived silently orphans everything the federation has already harvested.
