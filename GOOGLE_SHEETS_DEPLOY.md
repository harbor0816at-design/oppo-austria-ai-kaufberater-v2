# Deploy Google Sheets Source_B

The Source_B master sheet is:
https://docs.google.com/spreadsheets/d/1OWEWh1--R6txBCkVRlKXB5xGER4AGMXm2ldgHKGayYc/edit

## Backend Vercel environment variables

SOURCE_B_PROVIDER=google_sheets
GOOGLE_SHEETS_SPREADSHEET_ID=1OWEWh1--R6txBCkVRlKXB5xGER4AGMXm2ldgHKGayYc
GOOGLE_SHEETS_CACHE_TTL_SECONDS=300
GOOGLE_SHEETS_FAIL_OPEN=true

Add ONE of:
GOOGLE_SERVICE_ACCOUNT_JSON=<complete service-account JSON>
or
GOOGLE_SERVICE_ACCOUNT_JSON_B64=<base64 of complete service-account JSON>

Share the Google Sheet with the service account `client_email` as Viewer.

## Behavior

- No manual JSON upload is required.
- Consumer chat automatically reads the Sheet when the 5-minute cache expires.
- A successful refresh is persisted to SQL as the last-known-good fallback.
- Manual POST/DELETE /api/admin/facts is disabled in Google Sheets mode.
- Admin status: GET /api/admin/source-b/status
- Force refresh: POST /api/admin/source-b/refresh
- Both admin endpoints require X-Admin-Key.

## Validation completed before packaging

Backend: 10 tests passed
Backend compileall: passed
Frontend lint: passed
Frontend typecheck: passed
Frontend build: passed
