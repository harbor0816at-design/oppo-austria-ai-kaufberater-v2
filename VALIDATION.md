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

## Competitor source production checks

With `X-Admin-Key`, call:

```text
GET /api/admin/public-sources/status
```

Production-ready expectations:

- `official_direct_fetch_enabled = true`
- `official_reference_count > 0`
- `competitor_fact_count > 0`
- `ai_fact_source = false`
- `missing_fact_policy = exact_or_unknown`
- `source_order` starts with `official_manufacturer_live`
- `brave_configured = true` when `BRAVE_SEARCH_API_KEY` is configured; if false, official direct fetch and Sheet-B last-known-good still work, but Brave fallback is unavailable.

Manual black-box tests:

1. `Compare Find X9 Pro with Samsung Galaxy S26 Ultra.`
2. `What is the current Galaxy S26 Ultra battery and charging speed in Austria?`
3. `Give me the official links.`
4. `Compare Find X9 Pro with iPhone 17 Pro Max.`
5. `Xiaomi 17 Ultra vs Find X9 Ultra.`
6. Ask for a competitor field intentionally missing from `Competitor_Facts`; the assistant must say it is not currently verified rather than inventing a value.
