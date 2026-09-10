# Meta Lead Ads → Direct Demand CRM — Integration Spec

**Product:** Openhouse Direct Demand Dashboard (https://directdemand.vercel.app)
**Owner:** Rajnish (Growth)
**Status:** Ready for development
**Version:** 1.0 — Sep 2026

---

## 1. Problem & Goal

Meta lead ads currently have no direct pipe into our internal CRM. The old path
(Meta → Zoho Social → CRM) is dead: Zoho is disconnected, and the
"Zoho Social — Connected" label in Meta's Lead Ads CRM Setup is a stale record.
**Do not attempt to remove or rebuild it. It is not a dependency.**

**Goal:** Every lead submitted on a Facebook/Instagram lead form for the
Openhouse Page lands in the Direct Demand CRM within seconds, with full
campaign attribution, exactly once.

```
FB/IG Ad → Meta Lead Form → Meta leadgen webhook → Vercel API route
        → Graph API fetch (full lead) → Create Lead (internal) → CRM
```

## 2. What already exists (do not rebuild)

| Asset | Status |
|---|---|
| Meta Developer App "Openhouse Lead App" | Created, use case: *Capture & manage ad leads with Marketing API*. Unpublished / development mode — this is fine and intended. No App Review submitted (own-business assets only). |
| Permissions attached to app | leads_retrieval, pages_show_list, pages_read_engagement, pages_manage_ads, pages_manage_metadata (verify), ads_read, ads_management, business_management |
| System user + never-expiring token | Generated. Token, App ID, App Secret handed over privately by Rajnish. |
| CRM Create Lead capability | Exists in the Direct Demand app. This spec integrates with it, not around it. |

## 3. Scope

**In scope (v1):**
- Webhook endpoint on the production deployment (leadgen only)
- Handshake verification + payload signature validation
- Lead fetch from Graph API with attribution fields
- Idempotent lead creation (dedupe on `meta_lead_id`)
- Event log table for troubleshooting
- One-time Page subscription script
- Test procedure via Meta's Lead Ads Testing Tool

**Out of scope (v1):**
- Sending CRM outcomes back to Meta (Conversions API / conversion leads) — v2
- Historical lead backfill from Leads Center — separate one-off if needed
- Multi-page support (single Openhouse Page for now, but don't hardcode against it)

## 4. Environment & configuration

All secrets live in **Vercel → Project → Settings → Environment Variables**
(Production scope). Never commit them.

| Var | Value / source |
|---|---|
| `META_APP_ID` | From app Settings → Basic |
| `META_APP_SECRET` | From app Settings → Basic. Used only for signature verification. |
| `META_VERIFY_TOKEN` | Any random string we invent (e.g. `oh-dd-7c2f9a`). Must match what's typed into the Meta dashboard webhook config. |
| `META_ACCESS_TOKEN` | System-user token (`EAA...`), never-expiring |
| `META_GRAPH_VERSION` | `v23.0` (make it a var so upgrades are config-only) |

**Important Vercel constraints:**
- The webhook must live on the **production** URL. Preview deployment URLs
  change per deploy and are protected by Vercel auth — Meta cannot reach them.
  If Vercel "Deployment Protection" is enabled, exempt this route or use the
  production domain, which is public.
- Serverless timeout: keep the handler fast. Return `200` to Meta as soon as
  the event rows are stored/processed; total work (fetch + create) is 2 API
  calls and fits comfortably, but never do batch work in the webhook.

## 5. Data model

Add one table (Postgres/Supabase/whatever the app uses — adapt types):

```sql
CREATE TABLE meta_lead_events (
  id              BIGSERIAL PRIMARY KEY,
  meta_lead_id    TEXT UNIQUE NOT NULL,          -- dedupe key
  page_id         TEXT,
  form_id         TEXT,
  campaign_id     TEXT,
  campaign_name   TEXT,
  adset_id        TEXT,
  ad_id           TEXT,
  ad_name         TEXT,
  status          TEXT NOT NULL DEFAULT 'pending', -- pending|success|failed|duplicate
  attempts        INT  NOT NULL DEFAULT 0,
  error_message   TEXT,
  received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at    TIMESTAMPTZ,
  raw_webhook     JSONB,
  raw_lead        JSONB
);
```

On the CRM lead record itself, add/ensure these fields:
`meta_lead_id` (unique), `source = "Meta Lead Ads"`, `source_type = "facebook"`,
`form_id`, `campaign_id`, `campaign_name`, `adset_id`, `ad_id`, `ad_name`,
`lead_created_time`. These enable the eventual funnel:
Campaign → Ad Set → Ad → Lead → Visit → Booking → Sale.

## 6. Endpoint spec

**Route:** `POST|GET /api/meta/webhook` on the production domain.

### 6.1 GET — verification handshake (one-time)
Meta calls with query params `hub.mode=subscribe`, `hub.verify_token`,
`hub.challenge`. If `hub.verify_token === META_VERIFY_TOKEN`, respond `200`
with the **raw challenge string** as the body (plain text, nothing else).
Otherwise `403`.

### 6.2 POST — lead event
1. **Verify signature.** Header `X-Hub-Signature-256` = `sha256=` +
   HMAC-SHA256 of the **raw request body** using `META_APP_SECRET`.
   Compute over the raw bytes (in Next.js App Router: `await request.text()`
   before any JSON parsing). Reject mismatches with `403`. This is the only
   thing stopping randoms from injecting fake leads.
2. **Parse payload.** Shape:
   ```json
   { "object": "page", "entry": [ { "changes": [
       { "field": "leadgen",
         "value": { "leadgen_id": "...", "page_id": "...", "form_id": "...",
                    "created_time": 1234567890 } } ] } ] }
   ```
   Iterate every `entry[].changes[]`; ignore `field !== "leadgen"`.
3. **Upsert event row** on `meta_lead_id`. If a row already exists with
   `status = 'success'`, skip (Meta retry) — do not touch the CRM again.
4. **Process** (same invocation is fine at our volume):
   fetch → transform → create → mark `success`. Any thrown error → mark
   `failed` with `error_message`, increment `attempts`.
5. **Always return `200` JSON `{"status":"ok"}`** once events are recorded,
   even if processing of an individual lead failed — failures are retried by
   our own recovery path (see §9), not by making Meta re-send batches.

### 6.3 Lead fetch (Graph API)
```
GET https://graph.facebook.com/{VERSION}/{leadgen_id}
  ?fields=id,created_time,field_data,form_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name
  &access_token={META_ACCESS_TOKEN}
```
`field_data` format: `[{ "name": "full_name", "values": ["Rahul Sharma"] }, ...]`
Built-in names: `full_name`, `phone_number`, `email`, `city`. Custom questions
keep the key defined in the form builder — store all unmapped answers in a
`custom_answers` JSON field, never drop them.

### 6.4 Transform rules
- `phone`: strip spaces; strip leading `+91`; store 10-digit where possible,
  keep original in `raw_lead` regardless.
- `name` ← `full_name`; `email` ← `email`; `city` ← `city` (may be absent).
- Attribution fields copied verbatim from the fetch response.
- Map into whatever the existing Create Lead function/endpoint expects —
  **do not** invent a second lead-creation path. If Create Lead is currently a
  UI-only flow, extract it into a shared server function this route calls.

### 6.5 Duplicate policy
`meta_lead_id` is the idempotency key end to end. DB unique constraint is the
backstop; the status check in §6.2(3) is the fast path. A person submitting
two different forms = two leads (expected). Same `leadgen_id` twice = one lead.

## 7. Page subscription (one-time script)

After deploy + dashboard webhook verification, run once (script or `curl`):

```
# 1) exchange system-user token for the Page token
GET /{PAGE_ID}?fields=access_token&access_token={META_ACCESS_TOKEN}

# 2) subscribe the app to the Page's leadgen field
POST /{PAGE_ID}/subscribed_apps
     ?subscribed_fields=leadgen&access_token={PAGE_TOKEN}
# expect {"success": true}
```

Keep this as a script in the repo (`scripts/subscribe-page.ts`) so it's
re-runnable if the Page or app changes.

## 8. Meta dashboard configuration (done together with Rajnish)

1. App dashboard → **Webhooks** → object type **Page**.
2. Callback URL: `https://directdemand.vercel.app/api/meta/webhook`
   (or the custom production domain if one is attached — prefer that, since
   it won't change if the Vercel project is renamed).
3. Verify token: the `META_VERIFY_TOKEN` value. Click **Verify and Save** —
   must go green instantly.
4. Subscribe to the **leadgen** field.
5. Run the §7 subscription script.

## 9. Failure handling & recovery

- **CRM create fails / Graph fetch fails:** event row stays `failed` with the
  error. Recovery: an admin-triggered "Retry failed" action (or a small cron/
  Vercel scheduled function) that re-runs processing for `status='failed'`
  rows with `attempts < 5`.
- **Missed webhooks** (downtime, Meta hiccup): leads are retained by Meta for
  90 days. Recovery path: bulk read
  `GET /{FORM_ID}/leads` for the affected window and run the same
  transform/create path. Build this only if a gap actually occurs.
- **Token dies** (password change, security event — "never expire" is not a
  guarantee): every Graph call failure with an OAuth error should log loudly.
  Fix = generate a new system-user token, update the env var, redeploy.
- **Alerting:** at minimum, log `failed` events where they're visible in the
  dashboard; ideally a Slack/WhatsApp ping on first failure of the day.

## 10. Security requirements

- Signature verification (§6.2.1) is mandatory, not optional.
- Secrets only in Vercel env vars; no tokens in client-side code — this route
  must be a server function, and the token must never appear in the browser
  bundle.
- The endpoint accepts only GET (handshake) and POST (events); everything
  else → `405`.
- Log payloads server-side only; lead PII must not leak into client logs.

## 11. Test plan

1. **Handshake:** deploy, configure webhook in dashboard → Verify and Save
   turns green.
2. **Signature negative test:** POST junk without a valid signature → `403`,
   no rows created.
3. **Test lead:** Meta **Lead Ads Testing Tool** (developers.facebook.com/tools/lead-ads-testing)
   → select Openhouse Page + a form → Preview form → Create lead.
   Expect: event row `success` within seconds, lead visible in the CRM with
   source "Meta Lead Ads" and attribution fields populated (test leads may
   have null campaign ids — that's normal).
4. **Duplicate test:** use the tool's "Track status" / re-send, or POST the
   same recorded payload twice → exactly one CRM lead, second event skipped.
5. **Live smoke test:** one real form submission on a live ad → verify in CRM,
   then compare counts CRM vs Meta Leads Center daily for the first week.

## 12. Acceptance criteria

- [ ] A test lead from the Testing Tool appears in the Direct Demand CRM in < 30s
- [ ] The same `leadgen_id` delivered twice creates exactly one CRM lead
- [ ] Unsigned/mis-signed POSTs are rejected and create nothing
- [ ] Every event is visible in `meta_lead_events` with a terminal status
- [ ] Lead records carry `meta_lead_id`, form, campaign, adset, ad attribution
- [ ] All secrets live in Vercel env vars; none in the repo or client bundle
- [ ] Page subscription script exists in the repo and returns `success: true`
- [ ] One-week reconciliation: CRM lead count matches Meta Leads Center

## 13. Rollout checklist (order matters)

1. Migration: `meta_lead_events` table + new fields on lead record
2. Implement `/api/meta/webhook` (GET handshake, POST handler, transform, create)
3. Set env vars in Vercel (Production) → deploy
4. Dashboard: Verify and Save webhook, subscribe `leadgen` (with Rajnish)
5. Run Page subscription script → `{"success": true}`
6. Testing Tool lead → confirm in CRM
7. Leave running against live campaigns; daily count reconciliation for 7 days
8. v2 backlog: retry cron, missed-lead backfill command, Conversions API
   feedback loop for lead quality optimization

## 14. Open questions for the developer

1. What does the app use for persistence (Supabase/Postgres/other)? Adapt §5.
2. Is Create Lead currently a server endpoint or client-side logic? If
   client-side, extract to a shared server function first (§6.4).
3. Is a custom domain attached to the Vercel project? If yes, use it as the
   callback URL instead of `*.vercel.app`.
4. Is Vercel Deployment Protection enabled on production? If yes, exempt
   `/api/meta/webhook`.

---

*Reference implementation in Python/Django was shared separately
(`meta_leads_integration.py`) — logic and field mappings there are correct and
can be ported 1:1 to a TypeScript API route.*
