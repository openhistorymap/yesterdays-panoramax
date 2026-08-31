# Releasing

Publishing is automated by `.github/workflows/publish.yml` and uses PyPI
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — an OIDC token
minted per run, so no API token is stored in this repository.

## One-time setup

On PyPI, add a trusted publisher for the project:

| Field | Value |
| --- | --- |
| Owner | `openhistorymap` |
| Repository | `yesterdays-panoramax` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

Repeat on TestPyPI with the environment `testpypi`. Then create both
environments under **Settings → Environments** in the GitHub repository; adding
required reviewers to `pypi` is worth it, since a version cannot be reused once
it is taken.

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
