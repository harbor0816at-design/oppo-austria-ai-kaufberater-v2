# OPPO Austria AI-Kaufberater

Complete production-oriented monorepo for a conversational OPPO presales assistant.

## Included

- **Backend:** FastAPI, Pydantic v2, SQLAlchemy, LangGraph orchestration, optional Redis hot cache, DeepSeek V4 as the primary conversational intelligence, Google Sheets Source_B for official OPPO facts, optional Brave-powered live public search for current external facts, SSE, leads, audit logs, QPCR analytics and backend-managed Hero slides.
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

1. Google Sheets is the Source_B source of truth for current/official OPPO product, price, promotion and service facts.
2. DeepSeek is the main conversational intelligence and can answer ordinary/general questions directly from model knowledge.
3. Current OPPO-specific facts must come from Source_B; Source_B always overrides model memory.
4. Current external/competitor facts must come from live public search. Configure `BRAVE_SEARCH_API_KEY`; without it the assistant will not pretend model memory is current web data.
5. Use PostgreSQL in production. SQLite is only a safe local/fallback default.
6. Configure `DEEPSEEK_API_KEY` only in the backend project.
7. Hero slides are marketing content and remain separate from Source_B and conversation routing.

See [DEPLOY.md](DEPLOY.md) for exact deployment steps.
