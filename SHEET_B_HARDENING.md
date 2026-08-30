# Sheet-B hardening — Austria production rules

## Source of truth

Google Sheet `OPPO Austria AI-Kaufberater Source_B Master` is authoritative for current OPPO facts. AI is only an explanation, ranking, language and presentation layer.

## Production behavior

- Austria/EU is the default product market.
- Exact product facts are `exact_or_unknown`; no approximations.
- Missing OPPO fact => `currently not verified`, never model-memory fill-in.
- `LTPO not stated` means the assistant must not label the display LTPO.
- Prices/promotions are returned only when Source_B marks them current/public.
- Product, purchase and official-spec URLs are returned directly when the user asks for links.
- Competitor current facts require official/public verification.
- AI may explain the practical meaning of a verified parameter, but must not introduce a new product fact.

## Source_B tabs read by backend

- Products: exact AT/EU product facts
- Promotions: current store promotions only
- Services: Austria/Germany store and support facts
- Knowledge_FAQ: hard answer policies and local FAQs
- Competitor_References: curated source hierarchy/URLs for competitor validation

## Answer format

Default buying-advice answer: conclusion -> 3 relevant reasons -> trade-offs -> Austria purchase/service facts -> evidence -> clickable links. Large tables are opt-in, not default.

## Regression checks

- OPPO Find X9 Pro battery must come from Source_B (7500 mAh in current master).
- Asking whether Find X9 Pro is LTPO must not produce an LTPO claim because the Austria official spec does not state it.
- `Give me the official link` after an OPPO turn must route to Source_B and return an OPPO Austria URL.
- `直接给我他们的链接` after an OPPO-vs-competitor comparison must inherit recent context and return available verified links.
- eSIM / box contents / update-years questions must route to Source_B, not DeepSeek memory.
