# OPPO Austria AI-Kaufberater

Complete production-oriented monorepo for a conversational OPPO presales assistant.

## Included

- **Backend:** FastAPI, Pydantic v2, SQLAlchemy, LangGraph orchestration, optional Redis hot cache, DeepSeek V4 tool calling, Source_B guardrails, optional Brave-powered Source_A search, SSE, leads, audit logs, QPCR analytics and backend-managed Hero slides.
- **Frontend:** dependency-free responsive web UI, conversational timeline, automatic Hero carousel independent from chat, multilingual DE/EN/ZH UI, product cards, launch notification flow and an admin console.
- **CI:** Python 3.12 tests/compile plus dependency-free Node syntax/build checks. No npm lockfile, no npm cache and no `npm ci`.

## Repository layout

```text
backend/   FastAPI API; deploy as one Vercel project
frontend/  Static web UI; deploy as a second Vercel project
```

## Consumer URLs

- `/smartphone-finder/` — AI Kaufberater
- `/admin/` — Hero, Source_B, leads and AI-health administration

## Important production rules

1. Put real products into Source_B through `/admin/`; no demo SKU is seeded.
2. Use PostgreSQL in production. SQLite is only a safe local/fallback default.
3. Configure `DEEPSEEK_API_KEY` only in the backend project.
4. Source_A is independent from DeepSeek. Configure `BRAVE_SEARCH_API_KEY` for live public search; otherwise the assistant explicitly says that live public search is unavailable.
5. Hero slides are marketing content and remain separate from ProductFactSchema.

See [DEPLOY.md](DEPLOY.md) for exact deployment steps.
