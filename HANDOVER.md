# Direct Demand Dashboard — Engineering Handover

**Goal:** rebuild the working prototype as a production app — **React.js** frontend, **Python + FastAPI** backend, **existing Postgres** database — **keeping the interface exactly as it is today**.

- **UI source of truth:** `index.html` (the prototype). Its look, flows, copy, and interactions are the spec. Do **not** redesign.
- **Product/rules source of truth:** this doc + `Openhouse-Direct-CRM-PRD.md`. Where the prototype's UI has evolved past the PRD (noted below), **the prototype wins**.

---

## 1. Architecture

```
React SPA (Vite)  ──HTTPS/JSON──>  FastAPI (Python)  ──asyncpg/SQLAlchemy──>  Postgres (existing)
       │                                  │
       │                                  ├── Job worker (matching, TAT, +2h reminders, WhatsApp dispatch)
       │                                  ├── Integrations: Meta/GAds/portals, WhatsApp provider, Maps
       └── Google Maps JS API             └── Data feeds: Acquired Property Dashboard, Supply Closure Tracker
```

- **Auth:** JWT (access token) carrying `user_id` + `role`. Every request is role-scoped **server-side** (see §4). The prototype's role switcher becomes real login.
- **Existing Postgres:** confirm what already lives there (leads? users? inventory?). We **map to existing tables where they exist** and add the new ones below. Do not duplicate a leads table if one already exists — extend it.

---

## 2. Keeping the interface identical (critical)

The prototype is a single HTML file with an inline `<style>` block and HTML templates rendered by small JS functions. Port it like this:

1. **Lift the entire `<style>` block verbatim** into the React app as global CSS (`src/styles/app.css`). Keep every class name (`.stat`, `.card`, `.opt-row`, `.ms-panel`, `.office-pitch`, `.plan-chip`, `.wa-ico`, `.tat`, `.stage`, etc.). Do **not** swap to a component library.
2. **Fonts:** keep the Google Fonts link — Bricolage Grotesque, Hanken Grotesk, Spline Sans Mono.
3. **Icons:** keep the inline SVGs as-is (sidebar, WhatsApp logo `WA_SVG`, chevrons, etc.).
4. Each `tplXxx()` function in the prototype maps **1:1 to a React component** with the same DOM structure → identical rendering. The JS interactions (toggles, dropdowns, modals) become React state/handlers.
5. **CSS variables** (`:root { --bg, --emerald, --blue ... }`) are the design tokens — keep them.

Acceptance for "interface unchanged": a screenshot diff of each screen vs the prototype should be visually identical.

---

## 3. Screens, routes & flows

| Screen / route | What it shows | Key API calls |
|---|---|---|
| **Dashboard** `/` | "Hello, {user}" + 6 KPI cards: New, Qualified, Immediate Buyers, Follow-ups due Today, Pipeline, Converted. Cards are clickable → tabs. | `GET /metrics/dashboard` |
| **New Leads** `/leads/new` | Table: Lead (+source in brackets), City, Society (source), Config, Budget, **Plan to Buy**, Assigned To, WhatsApp. | `GET /leads?segment=new` |
| **Qualified Leads** `/leads/qualified` | Confirmed, active, **<7 days** since qualified. | `GET /leads?segment=qualified` |
| **Pipeline Leads** `/leads/pipeline` | Confirmed, active, **≥7 days** since qualified (auto-aged). | `GET /leads?segment=pipeline` |
| **Converted Leads** `/leads/converted` | Won. | `GET /leads?segment=converted` |
| **Lead Details** `/leads/:id` | Left: source-captured card (admin-edit), **Confirmed-on-call Q1–Q6**, Activity. Right: **Best matches from inventory (5)**, **From supply pipeline (5)** (expandable rows), Visit recordings. | `GET /leads/:id`, `GET /leads/:id/matches/*`, `PATCH /leads/:id/source-data`, `POST /leads/:id/confirm` |
| **Reminders** `/reminders` | Typed reminders (follow-up/visit/feedback/nego), filterable. Opened from the orange top-bar button. | `GET /reminders` |
| **Live Inventory** `/inventory` | Acquired property cards. | `GET /inventory` |
| **Supply Pipeline** `/supply` | MSI/token/negotiating units, buyer-interest tagging. | `GET /supply`, `POST /supply/:id/interest` |
| **Society Insights** `/societies` | Demand vs supply per society + **add buyer insights**. | `GET /societies/insights`, `POST /societies/insights` |
| **Gold Mine** `/goldmine` | Auto-bucket all leads against a new unit; bulk WhatsApp / call list. | `GET /buckets`, `POST /buckets/rematch`, `POST /buckets/:id/broadcast` |
| **Settings & Access** `/settings` | Integrations, API key/webhook, roles & assignment. | `GET/PATCH /settings/*`, `GET /users` |
| **Visit Planner** (modal) | Multi-stop route from inventory; Google Map + optimize; saves itinerary. | `POST /leads/:id/visits` |
| **Connect Meta** / **Add society insight** (modals) | As in prototype. | integration endpoints |

> **UI changes vs the original PRD** (prototype is current): lead detail is simplified (no stage dropdown / create-reminder / schedule-visit buttons / smart-summary / call-tracking card on that page); the confirmed-data form is now **Q1–Q6** (purpose, ₹→lacs budget, config incl. 3.5 BHK, multi-select societies, multi-select localities, office-visit Yes/No/Maybe with conditional date + pitch); **Plan to Buy** added to source data; **Closing Manager** role added; **7-day Qualified→Pipeline** rule added; matched inventory/supply lists live on the lead page.

---

## 4. Roles & access scope (enforce server-side)

| Role | Sees | Can edit |
|---|---|---|
| **Admin** | All leads | Source-captured data (only role), config, integrations, inventory |
| **Closing Manager (CM)** | All leads assigned to RMs in their team (multiple RMs per CM) | Confirmed data, stages of team leads |
| **RM** | Own (assigned) leads only | Confirmed data, stages of own leads |

- Implement as a **query filter** injected from the JWT: Admin → no filter; CM → `assigned_to IN (team RM ids)`; RM → `assigned_to = me`.
- **Hard rule:** `PATCH /leads/:id/source-data` → 403 unless Admin. The dormant Gold Mine pool is visible to Admin/CM, not individual RMs.

---

## 5. Postgres schema (proposed — reconcile with existing tables)

Add/extend. Names indicative.

```
users(id, name, phone, email, role['admin'|'cm'|'rm'], team_id→teams, active, password_hash, created_at)
teams(id, name, cm_user_id→users)

leads(id uuid, name, phone, source['meta'|'gads'|'99acres'|'magicbricks'|'youtube'|'whatsapp'|'api'|'webhook'|'sheets'],
      assigned_to→users, stage['new'|'contacted'|'visit_scheduled'|'visit_feedback'|'negotiation'|'won'|'lost'|'future_prospect'|'timepass'],
      tat_deadline, confirmed bool, qualified_at timestamptz, created_at, updated_at)

lead_source_data(lead_id→leads PK, budget_band, budget_min_lacs, budget_max_lacs, city, society, configuration, plan_to_buy)  -- ADMIN-write only
lead_confirmed_data(lead_id→leads PK, purpose['self_use'|'investment'], budget_value_lacs numeric, configuration,
                    office_willing['yes'|'no'|'maybe'], office_preferred_date, remark, confirmed_at)
lead_shortlist_societies(lead_id, society)     -- Q4 multi
lead_preferred_localities(lead_id, locality)   -- Q5 multi

lead_activity(id, lead_id, event, remark, actor_id→users, created_at)   -- the "Activity" timeline
reminders(id, lead_id, type['follow_up'|'visit_schedule'|'visit_feedback'|'negotiation'], note, due_at, done, auto_generated)

visits(id, lead_id, trip_date, rm_id→users, total_km, total_min, route_source['est'|'google'], self_schedule_token, status)
visit_stops(id, visit_id, inventory_id→inventory, seq)
recordings(id, lead_id, visit_id, file_ref, duration_sec, recorded_by→users, recorded_at)

inventory(id, name, society, city, budget_band, budget_min_lacs, budget_max_lacs, configuration, price, area, status, lat, lng,
          ext_source='acquired_property', synced_at)
supply_units(id, name, society, city, budget_band, budget_min_lacs, budget_max_lacs, configuration, price, area, eta,
             supply_stage['msi'|'token_paid'|'negotiating'], ext_source='supply_tracker', synced_at)
interests(id, supply_unit_id→supply_units, lead_id→leads NULLABLE, rm_id→users, note, created_at)

buckets(id, inventory_id→inventory NULLABLE, supply_unit_id→supply_units NULLABLE, created_at)
bucket_members(bucket_id→buckets, lead_id→leads, score int, matched_on text[])  -- ['society','budget','config','city']

society_insights(id, society, city, note, created_by→users, created_at)
localities(id, name, city)   -- reference for Q5
societies(id, name, city)    -- reference for Q4 / inventory
settings_integrations(key, value jsonb, enabled bool)
api_keys(id, label, hash, revoked, created_by)
```

**Budget representation:** source budget is a **band** (e.g. "₹70L – ₹90L") → store as `budget_min_lacs/budget_max_lacs`. Confirmed budget is a **single ₹ value** entered in the form → store `budget_value_lacs`. Matching uses numeric **range overlap** (see §6.4), not exact-band string equality.

---

## 6. Business rules / core logic (port exactly)

**6.1 Two-layer data.** Source-captured (`lead_source_data`, Admin-only) vs call-confirmed (`lead_confirmed_data`). Matching uses confirmed when present, else source.

**6.2 TAT.** New lead must be first-contacted within **1 hr** (configurable per source). `tat_deadline` set at creation; cleared on first confirm. States ok/warn/breach computed server-side (worker/scheduled), surfaced on dashboards.

**6.3 Qualify → 7-day auto-move (current behaviour).**
- On **confirm** (`POST /leads/:id/confirm`): set `confirmed=true`, `qualified_at=now()`, advance `new→contacted`, push activity.
- **Qualified segment** = `confirmed AND stage NOT IN (won,lost,future_prospect,timepass) AND now()-qualified_at < 7 days`.
- **Pipeline segment** = same but `≥ 7 days`. This is **purely date-driven** — a nightly job isn't required (compute in the query / a view), but a cron can also flip a flag if you prefer materialized state.

**6.4 Matching engine** (used by lead-detail matches **and** Gold Mine). City is a **hard filter**. A unit is a real match if **society matches OR (budget-range overlaps AND configuration matches)**. Score = city(40) + society(45) + budget(25) + config(20); rank desc; lead detail shows **top 5** inventory + **top 5** supply.

**6.5 Gold Mine.** On inventory/supply insert or update → worker re-scans all leads (active + dormant), rebuilds `buckets`/`bucket_members`. Bucket bulk actions: WhatsApp the unit to all members / push to a call list.

**6.6 Mandatory fields.** Confirm requires Q1 purpose, Q2 budget, Q3 config, Q6 office-willing → 422 with field errors otherwise. Stage changes require a remark (when stage UI is restored).

**6.7 Visit planner.** Multi-stop itinerary from inventory; distance/time = estimate (haversine × road factor) with optional Google **Directions** upgrade; "optimize route" = nearest-neighbour + 2-opt; saving → stage `visit_scheduled` + auto `visit_feedback` reminder +2 hr.

**6.8 Plan to Buy** (source field): within_30_days / 1–3 months / 3–6 months / just_exploring — colour-coded chip.

**6.9 Office-visit pitch** (Q6): on No/Maybe show the English + **Hinglish** pitch bullets (`{{City}}` = lead city); Preferred date shows on Yes/Maybe. This is static copy — keep verbatim from the prototype.

---

## 7. REST API surface (FastAPI)

All token-authed, role-scoped, JSON, standard error envelope `{detail, fields?}`.

```
# auth
POST   /v1/auth/login            → {token, user}
GET    /v1/me

# leads
GET    /v1/leads?segment=new|qualified|pipeline|converted&assigned_to=&city=
GET    /v1/leads/{id}            → source + confirmed + activity + matches + recordings + visits
POST   /v1/leads/ingest          → inbound (assign + TAT + WhatsApp alert)
PATCH  /v1/leads/{id}/source-data  (Admin → 403 else)
POST   /v1/leads/{id}/confirm      (Q1–Q6; 422 on missing; sets qualified_at)
POST   /v1/leads/{id}/stage        ({to_stage, remark})
GET    /v1/leads/{id}/matches/inventory   → top-5 ranked
GET    /v1/leads/{id}/matches/supply      → top-5 ranked

# reminders / visits / recordings
GET/POST /v1/reminders ; PATCH /v1/reminders/{id}
POST   /v1/leads/{id}/visits      (itinerary stops, returns self_schedule_token, +2h reminder)
POST   /v1/visits/{id}/recording

# inventory / supply  (synced from external dashboards)
GET    /v1/inventory ; GET /v1/supply
POST   /v1/supply/{id}/interest

# gold mine
GET    /v1/buckets
POST   /v1/buckets/rematch
POST   /v1/buckets/{id}/broadcast    (WhatsApp all / push to call list)

# society insights / metrics / admin
GET/POST /v1/societies/insights
GET    /v1/metrics/dashboard
GET/POST /v1/users ; GET/PATCH /v1/settings/*
```

---

## 8. Frontend structure (React + Vite)

```
src/
  styles/app.css              # the prototype's <style> block, verbatim
  lib/api.ts                  # fetch wrapper + auth token
  store/auth.tsx              # current user + role (replaces role switcher)
  router.tsx                  # routes from §3
  components/
    Sidebar, Topbar, KpiCard, StageChip, SrcBadge, TatChip, PlanChip,
    LeadTable, MultiSelectDropdown (.ms), OptionRow (.opt expandable),
    OfficePitch, Modal, Toast, WaButton
  pages/
    Dashboard, NewLeads, LeadsSegment (qualified/pipeline/converted),
    LeadDetail, Reminders, Inventory, Supply, SocietyInsights, GoldMine, Settings
  features/visitPlanner/       # modal + Google Maps + optimizer
```

- **Server state:** React Query (caching, refetch). **Auth/role:** context.
- **Maps:** Google Maps JS API key via env (`VITE_MAPS_API_KEY`); the planner code (haversine + 2-opt + Directions) ports directly.
- Each prototype `tplXxx()` → one page/component with identical markup.

---

## 9. Integrations & external data
- **Inventory** ← **Acquired Property Dashboard** (sync job → `inventory`). **Supply** ← **Supply Closure Tracker** (→ `supply_units`). Confirm: API, DB, or Sheet? read access?
- **Leads** ← Meta Lead Ads, Google Ads, 99acres/MagicBricks, YouTube, WhatsApp, webhook, API key, Google Sheets → `POST /leads/ingest`.
- **WhatsApp** provider (Kaleyra / Interakt / Cloud API) with approved templates (lead alert, brochure/unit broadcast); DLT/consent respected.
- **Google Maps** JS + Directions API (billing/key) for the visit planner.

---

## 10. Suggested build sequence
1. **Foundation:** repo (monorepo `apps/web` + `apps/api`), DB connection to existing Postgres, auth/login, port CSS + Sidebar/Topbar shell.
2. **Read paths:** leads list segments + Lead Details (read-only) + dashboard metrics → wire to DB.
3. **Write paths:** confirm (Q1–Q6) + qualify/7-day rule + source-data edit (Admin) + role scoping.
4. **Matching:** inventory/supply match endpoints + Gold Mine bucketing + worker.
5. **Reminders / Visit planner / Society Insights / Settings.**
6. **Integrations:** ingest + WhatsApp + inventory/supply sync.

---

## 11. Open items to confirm before/while building
- **Existing DB:** which entities already exist (leads, users, inventory)? schema to map onto?
- **Data sources:** Acquired Property Dashboard + Supply Closure Tracker — API/DB/Sheet + access.
- **WhatsApp provider** + approved templates + DLT.
- **Auth:** how users log in (phone+OTP like your other tools? email/password? SSO?).
- **Gold Mine rules:** multi-bucket membership (current: a lead can be in several) vs single best; auto-bucket vs RM-confirm before broadcast.
- **Budget matching:** confirm numeric range-overlap (see §5/§6.4).
- Restore-or-drop on the lead page: stage control, create-reminder, schedule-visit, call-tracking (data model keeps them; UI entry points were removed).

---

*UI = `index.html` (verbatim). Rules = this doc + PRD. Stack = React + FastAPI + existing Postgres.*
