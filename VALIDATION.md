# Validation performed before packaging

The complete repository was validated from its final source tree with:

```text
Backend:
- python -m compileall -q app tests app.py
- pytest -q
- FastAPI TestClient smoke test for /, /healthz, Hero fallback, admin auth,
  Source_B upsert, product list and SSE chat

Frontend:
- npm install --package-lock=false --no-audit --no-fund
- npm run lint
- npm run typecheck
- npm run build
```

The frontend intentionally has no external runtime dependencies and no
package-lock.json, eliminating the previous npm cache/lockfile/ESLint-path CI
failures.
