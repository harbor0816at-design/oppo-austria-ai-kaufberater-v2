# Presales FAQ database routing

The presales advisor now checks this Google Sheet before any DeepSeek answer:

- Spreadsheet ID: `1MBk3s272IhbcJSXTIp16oPuKA2Su9dNbHeHEY_qmI38`
- Workbook title: `OPPO Austria Smart Advisor Product KB｜中德英三语商品数据库`

## Routing order

1. Search the FAQ/KB workbook conservatively by product name, exact question and maintained keywords.
2. If a FAQ/KB match is found, return the database text directly. DeepSeek is not called and does not rewrite the answer.
3. If there is no FAQ/KB match, continue to the existing main-agent workflow:
   - OPPO current facts -> Source_B
   - competitor/current facts -> official live source / Brave / verified cache
   - stable general knowledge -> DeepSeek

This means FAQ is an answer priority layer, not a replacement for Source_B or current competitor verification.

## Indexed sheets

- `Service_Policy`: shipping, returns, replacement, warranty, showroom, customer service, payment, invoice, trade-in and data migration.
- `Product_KB`: product specs, battery, charging, display, camera, box contents, SIM/eSIM/connectivity, recommendation reason and caveats.
- `Compatibility_Map`: phone/watch/earbud/device/OS compatibility and feature limitations.
- `Competitor_KB`: verified competitor product specs and strengths/weaknesses. Dynamic price/stock/promotion questions are intentionally excluded from FAQ direct-answer routing and continue to live verification.
- `OPPO_Competitor_Map`: balanced OPPO-vs-competitor trade-offs when both products are explicitly mentioned. Dynamic-price questions continue to live verification.
- `Consumer_Decision_Playbook`: close/exact consumer-decision questions.

## Conservative matching

A product name alone does not trigger a FAQ response. It must be accompanied by a maintained factual topic such as battery, charging, display, camera, box contents, eSIM, compatibility, warranty, etc.

If the matcher is uncertain, it returns no hit and the turn goes to DeepSeek. This is deliberate: false FAQ hits are worse than a model fallback.

## Admin diagnostics

- `GET /api/admin/faq/status`
- `POST /api/admin/faq/refresh`

Both require `X-Admin-Key` through the existing admin authentication.
