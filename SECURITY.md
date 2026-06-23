# Security Policy

## Reporting a vulnerability
Email **support@openhouse.in** with details and steps to reproduce. Please do not
open public issues for security reports. We aim to acknowledge within 3 business days.

## Production security posture
- **Fail-closed config** (`APP_ENV=prod`): the API refuses to boot with a default
  `JWT_SECRET`, missing `GOOGLE_OAUTH_CLIENT_ID` (which would leave auth open), an
  empty/localhost `CORS_ORIGINS`, or a missing `DATABASE_URL`.
- **AuthN/Z**: Google OAuth (verified server-side) → short-lived JWT; role-scoped
  (`admin`/`cm`/`rm`); `@openhouse.in` domain restriction.
- **Transport/headers**: HSTS (prod), `X-Frame-Options: DENY`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy`, and a strict `Content-Security-Policy`.
- **Rate limiting** (slowapi): global default + a strict limit on `/v1/auth/google`.
  Redis-backed across instances when `REDIS_URL` is set, else in-memory.
- **CORS**: explicit methods/headers, no credentials (Bearer-token auth), Vercel
  previews via `CORS_ORIGIN_REGEX`.
- **Input**: Pydantic validation; SQL is fully parameterized; request bodies capped
  (`MAX_BODY_BYTES`). Swagger docs are disabled in prod.
- **Secrets**: never committed (`.gitignore` covers `.env`, `service-account*.json`).
  Provided via Render/Vercel env + GitHub Secrets. Server-to-server keys
  (`CRM_API_KEY`) are never sent to the browser.

## CI security gates
Every PR runs: secret scan (**gitleaks**, blocking), dependency audits
(**pip-audit**, **npm audit**), Python SAST (**bandit**), filesystem scan (**Trivy**),
and **CodeQL** (Python + JS/TS). Dependabot keeps deps/actions/base-images current.

## Secret rotation
Rotate immediately if a secret is exposed (e.g. printed in logs/terminal):
`CRM_API_KEY`, `DATABASE_URL` / `PROPERTIES_DATABASE_URL` credentials, and the
Google Maps keys (re-issue + restrict the frontend key by HTTP referrer, keep the
server Geocoding key separate). Update the values in Render/Vercel + GitHub Secrets.
