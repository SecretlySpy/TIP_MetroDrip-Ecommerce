# Branch protection on `main` (required — human action)

CI already runs the `qa` job on every push/PR (`.github/workflows/ci.yml`).
**Without branch protection, a red CI check does not stop merges.** That is how
Python-2 `except A, B:` reached `main` five times.

## Required settings

GitHub → **Settings → Branches → Add branch protection rule** (or edit `main`):

| Setting | Value |
|---|---|
| Branch name pattern | `main` |
| Require a pull request before merging | **On** |
| Require status checks to pass before merging | **On** |
| Status checks that are required | **`qa`** (from workflow CI) |
| Require branches to be up to date before merging | **On** |
| Do not allow bypassing the above settings | **On** (Include administrators) |
| Restrict who can push to matching branches | optional but recommended |

## Prove the gate (after protection is on)

```bash
git checkout -b chore/deliberate-syntax-fail
# introduce a SyntaxError in apps/
git commit -am "test: deliberate syntax error for branch protection"
git push -u origin HEAD
gh pr create --fill
# Expected: PR cannot merge — qa fails or required check pending/failed
gh pr close --delete-branch
```

## Local first line of defence

```bash
pre-commit install
python -m compileall -q apps config jobs tests manage.py services
pytest tests/test_source_compiles.py
```

**Note (Python 3.14 / PEP 758):** unparenthesized `except A, B:` is *syntactically*
valid again on 3.14. Project rule still requires `except (A, B):` for portability
and clarity; ruff `target-version = "py313"` keeps the formatter from stripping
parentheses. `compileall` alone is no longer sufficient to catch that style on 3.14 —
rely on ruff format check + code review + this protection rule.
