# Working on Review Insights

Review Insights turns Google Play reviews into design and product decisions: a FastAPI backend (`backend/`),
a React + TypeScript frontend (`web/`), offline tests (`tests/unit/`). See README.md for the product.

## Rules

### After every push, follow CI until it is green
1. Push, then find the run for the pushed commit (`gh run list --limit 5`) and watch it to the end
   (`gh run watch <id> --exit-status`).
2. If any job fails, read the log (`gh run view <id> --log-failed`), fix the cause, commit, push, and watch the
   new run. Repeat until every job passes.
3. Never report work as done while its CI run is red or still running.

### Before every commit, run the same checks CI runs and check the real exit codes
- `.venv/bin/ruff check backend tests` and `.venv/bin/ruff format --check backend tests`
- `.venv/bin/python -m pytest -q` (look at the exit code, not just the last line of output)
- In `web/`: `npx tsc --noEmit` and `npx vite build` (Node 24: `nvm use`)

### Secrets
- Never commit `.env`, `data/` (database, encrypted key vault, ChatGPT tokens) or key files; check
  `git status` before committing.
- API keys belong in the encrypted vault (`backend/services/vault.py`), never in browser storage or logs.

### Product conventions
- Every AI claim must cite real reviews; validate citations in code and drop invented ones.
- Compute numbers and labels (priority, better/worse) in code; let the model write, not count.
- Tests must not touch the real keychain or `data/` folder (use `Settings(use_keychain=False, data_dir=tmp_path)`).
