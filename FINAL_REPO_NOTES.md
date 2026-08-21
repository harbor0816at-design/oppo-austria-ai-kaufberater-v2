# Final repository notes

This repository is self-contained and intentionally keeps both backend dependency formats:

- `backend/requirements.txt` + `backend/requirements-dev.txt` for GitHub Actions/Vercel.
- `backend/pyproject.toml` for editable installs such as `pip install -e '.[dev]'`.

The only workflow file should be:

`.github/workflows/ci.yml`

It supports automatic runs on `main`/`master` and manual `Run workflow` through `workflow_dispatch`.

Do not add another CI workflow copied from an older repository.
