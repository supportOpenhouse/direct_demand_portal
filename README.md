# Direct Demand Dashboard

A standalone, self-contained prototype for **Openhouse Direct Demand** — the direct-buyer
lead & inventory engine for Delhi NCR (Gurgaon, Noida, Ghaziabad).

> This is a **new and separate** dashboard. It is built from the `Openhouse-Direct-CRM-PRD.md`
> handoff and the original `openhouse-crm.html` prototype, rebuilt with a refined, semantic
> colour system.

## The app (phase 1 — Live Inventory + Supply Pipeline)

React (Vite) frontend + FastAPI backend. Two tabs are live; the rest are styled stubs.

- **Live Inventory** — synced from the private Acquired Property Google Sheet into Neon
  Postgres (on startup, every `SYNC_INTERVAL_MINUTES`, and via `POST /v1/inventory/sync`).
  The whole sheet row is kept in a `raw` JSONB column, so sheet column changes never break
  the sync — only the display mapping (`HEADER_ALIASES` in
  `backend/app/services/inventory_sync.py`) may need a tweak.
- **Supply Pipeline** — read live (read-only) from the external properties DB, showing rows
  with `stage` in: Draft, Visited, Deal Terms, AMA Req, AMA Signed, Token. Contact/owner
  columns are never exposed by the API.

### Setup

```bash
cp .env.example .env        # fill in DATABASE_URL, PROPERTIES_DATABASE_URL,
                            # GOOGLE_SERVICE_ACCOUNT_JSON (path or inline JSON), SHEET_ID
```

The service-account **email must be granted Viewer access on the sheet**. The app boots fine
with an empty `.env` — endpoints report `not_configured` instead of crashing.

### Run (dev)

```bash
cd backend  && uv sync     && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev          # http://localhost:5173
```

API: `GET /v1/health` · `GET /v1/inventory` · `POST /v1/inventory/sync` · `GET /v1/supply`.
Tests: `cd backend && uv run pytest`.

### Deploy — backend on Render, frontend on Vercel

**Backend (Render):**

1. Render dashboard → **New → Blueprint** → select this repo (it picks up `render.yaml`),
   or create a **Web Service** manually with: root dir `backend`, build
   `pip install uv && uv sync --frozen`, start
   `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/v1/health`.
2. Set env vars in the dashboard: `DATABASE_URL`, `PROPERTIES_DATABASE_URL`,
   `GOOGLE_SERVICE_ACCOUNT_JSON` (**paste the full JSON inline** — there's no file on Render;
   the app parses values starting with `{` as JSON), `SHEET_ID`, `SYNC_INTERVAL_MINUTES`,
   and `CORS_ORIGINS` (your Vercel URL, comma-separated to include previews).
3. Note your service URL, e.g. `https://direct-demand-api.onrender.com`.
4. Free tier sleeps after idle (cold start ≈30s; the sheet re-syncs on every wake). Use the
   Starter plan to keep the 15-min sync schedule alive around the clock.

**Frontend (Vercel):**

1. Vercel → **Add New Project** → import this repo → set **Root Directory = `frontend`**
   (framework auto-detects as Vite; build `npm run build`, output `dist`).
2. Add env var `VITE_API_URL=https://direct-demand-api.onrender.com` (no trailing slash).
3. Deploy. `frontend/vercel.json` already rewrites all routes to `index.html` so
   react-router deep links (`/inventory`, `/supply`) work.
4. Copy the production domain back into the backend's `CORS_ORIGINS` on Render.

## How lead → property matching works

When a buyer's requirement is known (society, area, budget, BHK), every available unit gets a
**score** and the top 5 are shown — on the lead detail and live as the call form is filled.
Code: `backend/app/services/matching.py` (`match_lead` / `match_preview`).

### In plain English

Every property earns points; more points = better fit:

| Signal | Points | Why |
|---|---|---|
| Same society they asked for | **+30** | strongest signal |
| Inside their budget | **+20** | closer to their exact figure scores higher |
| Same sub-area / micro-market | **+15** | |
| Same locality | **+12** | |
| Same BHK | **+10** | |
| Same city | **+5** | baseline |

And it searches in order, stopping once it has 5 — a stronger tier always beats a weaker one,
and within a tier the higher score wins:

1. their **exact society**
2. their **same area** (micro-market / locality) with budget or BHK matching
3. **same city** + budget **and** BHK
4. **same city** + budget **or** BHK
5. anything else in the **same city**

> Simple rule: a unit in their exact society always ranks above one that's only in the same
> city, and within each group the one closest to their budget wins — so the buyer sees the
> most relevant options first, not a random list.

### The exact mechanics

- **Geo anchor** comes from `master_societies.micro_market` (the buyer's societies are looked
  up to find their micro-markets; candidate units are enriched the same way).
- **Budget window** = the confirmed figure ±20%; *budget closeness* is continuous — `1.0` at
  the exact figure, decaying to `0` at the window edge (a band like "Up to ₹75L" is parsed to a
  range). So "inside budget" isn't binary; nearer = more points.
- **Score** = `3.0·society + 2.0·budget_closeness + 1.5·micro_market + 1.2·locality + 1.0·BHK
  + 0.5·city` (the table above is this, scaled for explaining).
- **City** is a hard filter when the lead has one. Confirmed call data (Q1–Q6) overrides the
  source-captured data when present.
- Units are **cached in-memory (90s)** so the live preview recomputes on every keystroke
  without re-hitting the databases.

This is adapted from the seller-flow "Similar Properties v2" ladder, kept to the parts that fit
buyer-lead matching (tiered fill so we always surface up to 5, continuous budget closeness,
micro-market geo anchor, match reasons) and dropping the seller-only bits.

## Visit planner (Google Maps)

The 📅 Visits button (on the lead lists and lead detail) opens a multi-stop route planner:

- **Start = the RM's current location** (browser geolocation).
- **Stops** are picked from **live inventory** — units are geocoded server-side
  (`backend/app/services/geocode.py`, Google Geocoding API, cached in `geocode_cache`)
  so they have coordinates; the sync re-applies cached coords instantly on every run.
- **"Optimize route"** reorders the stops for the shortest trip from the start, regardless of
  the order they were picked (nearest-neighbour + 2-opt, `frontend/src/lib/geo.ts`).
- The **Google Map** draws the live driving route via the Directions API and shows total
  distance/time; without a key it falls back to a straight-line estimate.
- Saving stores the plan (`visits` table) and moves the lead to **Visit Scheduled**.

**Keys** (Google Cloud Console — one key with all three APIs enabled is fine):
`MAPS_API_KEY` (backend, **Geocoding API**) and `VITE_MAPS_API_KEY` (frontend, **Maps
JavaScript API** + **Directions API**). Add the Vercel domain + `http://localhost:5173` to the
frontend key's HTTP-referrer restrictions.

## The prototype (UI reference)

`index.html` is the single-file design prototype — the pixel spec for every screen. The React
app lifts its `<style>` block verbatim (`frontend/src/styles/app.css`) and ports its markup
1:1. To view it, just `open index.html` in a browser.

## What changed vs. the source prototype

The functionality and flow are faithful to the PRD and the original prototype. The work here
is the **colour coding** — moved from a warm cream/paper theme to a cleaner cool canvas so the
semantic colours read clearly and consistently:

- **Canvas** — cool near-white (`#f5f7fa`) instead of warm cream, so colour-coded chips pop.
- **Stages** — a logical hue ramp across the pipeline:
  `New (blue) → Contacted (cyan) → Visit Scheduled (amber) → Visit Feedback (violet) →
  Negotiation (indigo) → Won (emerald)`, plus terminal states
  `Lost (red)`, `Future Prospect (gold)`, `Timepass (slate)`.
- **TAT** — a strict traffic-light scale: `ok = green`, `warn = amber`, `breach = red (pulsing)`.
- **Sources** — kept on recognisable brand colours (Meta blue, Google Ads green, 99acres
  orange, MagicBricks magenta, YouTube red, WhatsApp green) with harmonised soft backgrounds.
- **Gold Mine** — anchored to a single honey-gold so buckets, tags and the re-activation
  engine read as one coherent system.
- Stat cards now carry a coloured left accent matching the metric's meaning, and the pipeline
  funnel uses the same stage hues.

All colours are CSS custom properties under `:root` in `index.html`, so re-theming is a
single block to edit.

## Features in the prototype

Mirrors the PRD modules:

- **Dashboard** — a New → Qualified → Pipeline → Converted funnel, a "leak-detector" signal
  row (Follow-ups due / Uncontactable / Immediate buyers), "leads needing action now", a
  pipeline funnel, the **Follow-up radar**, and a **Why we lose leads** breakdown (see below).
- **Qualified / Pipeline / Converted Leads** — the leads list, split into three sidebar tabs
  (qualified = confirmed on call; pipeline = contacted→negotiation; converted = won). The four
  Dashboard stat cards are clickable and jump to the matching tab; **New Leads** has no tab
  (it lives in "Leads needing action now" on the Dashboard, highlighted with a moving light).
  Click any lead for the two-layer data model (source-captured vs call-confirmed),
  mandatory-field validation, call tracking + follow-up, typed reminders, stage history with
  mandatory remarks, AI smart summary, matched live inventory, the visit planner, and recordings.
- **Reminders** — typed (follow-up / visit schedule / visit feedback / negotiation), filterable.
  Opened from the **orange Reminders button in the top bar** (left of "Add New Lead").
- **Live Inventory** — resale & available units with one-tap WhatsApp brochure share.
- **Supply Pipeline** — MSI / token-paid / negotiating units with buyer-interest tagging.
- **Society Insights** — demand (buyers, active + dormant) vs. live supply (units) per society,
  with a demand-gap and "high-demand" flags to show which societies to source next. Add
  free-form **buyer insights** (what buyers commonly ask — RERA, possession, facing/floor
  availability, connectivity, price trend) for any society via "+ Add society insight".
- **Gold Mine** — auto-bucketing of all leads against new inventory (city hard filter, then
  society OR budget+config), with bulk WhatsApp / push-to-call actions.
- **Settings & Access** — no-code integrations, API key / webhook, roles & assignment rules.
- **Roles & access scope** (switch personas via the user chip, bottom-left):
  - **Admin** — all leads; the only role that edits source-captured data & config.
  - **Closing Manager (CM)** — all leads assigned to the RMs in their team (multiple RMs report
    into one CM).
  - **RM** — their own (assigned) leads only.
  Every list, the dashboard counts, nav badges, Gold Mine and Society Insights are filtered to
  the current user's scope. Source-captured data stays Admin-edit-only.
- **Add New Lead** (top bar) and **Connect Meta Leads** demonstrate ingestion, TAT and
  WhatsApp alerts.

## Visibility features (from the live-sheet audit)

Added after auditing the team's real working Google Sheet, which showed *why* leads were being
wasted: 9 different table layouts, freeform statuses, and critical follow-ups/requirements
buried in a Remarks column. Each feature plugs a specific leak:

- **A — Follow-up / Callback radar.** Every lead carries a `next callback` (overdue / today /
  upcoming). The dashboard surfaces a "Follow-ups due" tile + a radar list (overdue-first, with
  one-tap Call). Fixes the biggest leak: "call back next month" notes that used to rot in the sheet.
- **B — Standard stage + call outcome.** Alongside the stage enum, each lead records a **last
  contact outcome** (Connected / Ring-no-response / Busy / Switched-off / Not-reachable) and an
  **attempts** counter, shown as chips in the leads list and editable in the lead's
  *Call tracking & follow-up* card. A dashboard tile counts "Uncontactable — needs retry".
- **D — Immediate-buyer (🔥) flag.** Hot/ready buyers are flagged with a flame in the list, lead
  header and radar, and counted in an "Immediate buyers" tile so they jump the queue.
- **E — Loss-reason analytics.** Marking a lead **Lost** now requires a structured reason, typed
  as **operational** (ground-team no-show, broker, missed follow-up — *recoverable*) or
  **genuine** (bought elsewhere, budget, requirement unavailable). The dashboard's *Why we lose
  leads* card splits the two so operational losses get fixed instead of written off.

## Multi-stop visit planner (Google Maps)

Available against **any lead** — the "📅 Schedule visit" button on the lead detail and a
"📅 Visits" quick-action on every row of the Leads list open a route planner that lets an RM:

- Add multiple properties from inventory as an ordered itinerary — **Visit 1, Visit 2, Visit 3…**
  (reorder ↑/↓, remove, city-filtered to the lead's city).
- See **distance & drive-time between each stop** and the **trip totals** (km, time, # stops).
- **Optimize route** — one click reorders the selected stops into the shortest trip
  (nearest-neighbour + 2-opt on the stop coordinates), and reports the km/time saved. Works on
  the estimates now; with the Directions API enabled it reflects real driving distances.
- Plot every stop on a **Google Map** with numbered pins and the driving route.
- Save the plan to the lead (moves it to *Visit Scheduled*, logs the itinerary in history, and
  auto-creates the +2 hr feedback reminder).

### Enabling the map

Open `index.html` and paste your key into the constant near the top:

```js
const MAPS_API_KEY = ""; // ← your Google Maps JavaScript API key (billing enabled)
```

- **Without a key:** the planner still works — itinerary, distance and drive-time are shown as
  estimates (straight-line × road factor); the map area shows a placeholder.
- **With a key:** the live Google Map renders with numbered pins. If the **Directions API** is
  also enabled on the key, the route + per-leg distance/time switch to real driving values
  automatically (otherwise it stays on the estimate).

Inventory units carry approximate `lat`/`lng` per society (Delhi-NCR) for the pins and math.

## Status

`v0.3` — prototype / front-end reference only. Mock data lives inline in `index.html` (seeded
lost leads for the loss analytics; approximate inventory coordinates for the map). No backend
yet. See `Openhouse-Direct-CRM-PRD.md` for the data model, REST API, integration contracts,
business rules and acceptance criteria when the backend build begins.
