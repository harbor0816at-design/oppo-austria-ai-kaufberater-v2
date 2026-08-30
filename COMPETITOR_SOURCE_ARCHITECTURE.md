# Competitor evidence architecture

Production comparison facts use a strict evidence chain. DeepSeek is never a competitor fact source.

## Source order

1. **Official Austria/EU live page** — direct HTTP fetch from a manufacturer URL curated in `Competitor_References` or a product URL in `Competitor_Facts`.
2. **Brave official-domain fallback** — if the direct page is blocked/unavailable, Brave Search runs constrained to the approved manufacturer domain.
3. **Sheet-B verified competitor facts** — `Competitor_Facts` is the last-known-good normalized store. Blank fields stay unknown. `ai_may_infer_missing_facts=FALSE`.
4. **General Brave public evidence** — independent/review context only when no official/verified competitor result exists. It cannot override OPPO Source_B or verified manufacturer facts.

## Roles

- `Products`: authoritative Austria/EU OPPO facts.
- `Competitor_References`: approved official manufacturer discovery/spec URLs and independent review references.
- `Competitor_Facts`: normalized, manually verified Austria competitor facts with verification date and direct official URLs.
- DeepSeek: understands intent, explains trade-offs, translates facts into user meaning, and writes the final answer. It must not create a missing specification.

## Live fetch safety

Only HTTPS public URLs on approved manufacturer domains are followed. Private, loopback, link-local and localhost targets are rejected. Official HTML is reduced to bounded evidence text; arbitrary HTML is not converted automatically into Source_B facts.

## Runtime cache

Official page fetches are cached for 6 hours by default (`COMPETITOR_OFFICIAL_CACHE_TTL_SECONDS=21600`) to reduce latency and manufacturer-site load.

## Brave

`BRAVE_SEARCH_API_KEY` is optional for the primary official direct-fetch path, but required for the Brave fallback. Without a key, the system still uses direct official pages and verified `Competitor_Facts`.

## Operations health endpoint

`GET /api/admin/public-sources/status` (requires `X-Admin-Key`) exposes whether direct official fetch is enabled, whether Brave is configured, how many official references and verified competitor facts are loaded from Sheet-B, freshness counts, approved official domains, and the exact evidence priority chain. It never exposes API keys.
