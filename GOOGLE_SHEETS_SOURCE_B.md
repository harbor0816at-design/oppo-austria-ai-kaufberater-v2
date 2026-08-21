# Google Sheets Source_B

The production Source_B master is now the private Google Sheet:

https://docs.google.com/spreadsheets/d/1OWEWh1--R6txBCkVRlKXB5xGER4AGMXm2ldgHKGayYc/edit

## Runtime model

- Google Sheet = source of truth maintained by the operations team.
- Vercel Backend reads Products / Promotions / Services automatically.
- Redis or in-memory cache keeps a 5-minute snapshot.
- Every successful sheet refresh is also persisted to the SQL database as a last-known-good fallback.
- Manual POST/DELETE `/api/admin/facts` is disabled while `SOURCE_B_PROVIDER=google_sheets`.
- Consumer chat automatically refreshes after the cache TTL; there is no local JSON upload workflow.

## One-time Google authentication

1. Create a Google Cloud service account.
2. Enable the Google Sheets API.
3. Create a JSON key for the service account.
4. Share the Source_B Master Sheet with the service account `client_email` as **Viewer**.
5. In the Vercel Backend project, add either:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = the complete JSON key, or
   - `GOOGLE_SERVICE_ACCOUNT_JSON_B64` = base64 of that JSON.
6. Keep `SOURCE_B_PROVIDER=google_sheets`.

The Sheet stays private. Do not publish it to the web, because future Source_B rows may contain pre-order or confidential fields.

## Admin checks

- `GET /api/admin/source-b/status` with `X-Admin-Key`
- `POST /api/admin/source-b/refresh` with `X-Admin-Key`

A normal consumer query also triggers a refresh automatically when the 5-minute cache expires.
