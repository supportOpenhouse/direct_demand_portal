# Lead stage model — make `stage` authoritative

**Date:** 2026-07-29
**Status:** approved, ready for implementation plan

## Problem

`stage` does not decide which page a lead appears on. The tabs are SQL predicates in
`SEGMENTS` (backend/app/routers/leads.py) over `confirmed`, `follow_up_at`,
`qualified_at` and the `crm_visits` table, with `stage` as only one input.

Three consequences:

1. **Leads can fall through every tab.** The `pipeline` predicate carries an explicit
   "safety net" clause whose stated purpose is to catch leads that match no other tab.
   A patch over a structural hole, not a feature.
2. **The DB doesn't match the UI.** The dashboard's 159 "qualified" is not a stage —
   it is `confirmed = true AND qualified_at IS NOT NULL`, spread across the `new` and
   `contacted` stages.
3. **Dead-end state.** `visit_planned` marks an internal trip plan that is not an
   appointment, parking the lead in a stage nobody works.

## Current data (1,587 leads)

| stage | count |
|---|---|
| new | 1000 |
| rejected | 406 |
| contacted | 150 |
| visit_scheduled | 20 |
| visit_planned | 9 |
| rnr | 2 |

`contacted` (150) + `visit_planned` (9) = **159**, exactly the dashboard's qualified
count. Confirms every qualified lead is in one of those two stages and none hide at
`new`. `won`, `lost`, `future_prospect` and `timepass` are declared in code but hold
zero leads.

## Target model

### Stages (8)

```
new · call_not_received · follow_up · qualified · visit_scheduled · won · rejected · rnr
```

Removed: `visit_planned`, `contacted`, `lost`, `future_prospect`, `timepass`.

`call_not_received` vs `follow_up`: **never connected vs connected.** A lead we have
called but never reached is `call_not_received`; one we have spoken to and owe a
callback is `follow_up`. This matches the existing RNR escalation, which already
counts consecutive misses only on never-connected leads.

### Pages (7)

Each page is `WHERE stage = ...`. A lead appears on exactly one.

| Page | Route | Stage |
|---|---|---|
| New Leads | `/leads/new` | `new` |
| Call Not Received | `/leads/call-not-received` | `call_not_received` |
| Follow Up | `/leads/followup` | `follow_up` |
| Qualified Leads | `/leads/qualified` | `qualified` |
| Pipeline Leads | `/leads/pipeline` | `visit_scheduled` |
| Converted Leads | `/leads/converted` | `won` |
| Rejected Leads | `/leads/rejected` | `rejected` OR `rnr` |

RNR leads keep `stage = 'rnr'` and carry an RNR badge on the Rejected page. The
`/leads/rnr` route redirects to `/leads/rejected` so existing links survive.

### Transitions

Every write sets `stage` explicitly. No stage is inferred at read time.

| Action | Resulting stage |
|---|---|
| Call connected | `follow_up` (unless already past it) |
| Confirm on call, `qualify=true` | `qualified` |
| Confirm on call, `qualify=false` | `follow_up` |
| Call missed, `ever_connected = false` | `call_not_received` |
| Call missed, `ever_connected = true` | `follow_up` |
| 10th consecutive miss, never connected | `rnr` |
| Miss reason `Invalid Number` | `rejected` |
| Manual callback set (post-connect) | `follow_up` |
| Visit booked on Openhouse app | `visit_scheduled` |
| Rejected by user | `rejected` |
| Trip plan saved | **unchanged** |

"Call connected" needs the guard because the caller may abandon before filling the
confirm form. Without it a `call_not_received` lead that finally answers keeps that
stage while `ever_connected` becomes true — stage contradicting the data, the exact
failure this change exists to remove. It only ever moves a lead forward:
`new` and `call_not_received` become `follow_up`; `qualified`, `visit_scheduled` and
`won` are left alone.

### Visit planning

`visit_planned` is deleted as a stage. The route planner, the saved-plan card and the
plan endpoints all stay, and a saved plan still persists — it simply no longer moves
the lead. Only a real booking (`POST /v1/visits/book`) sets `visit_scheduled`.

When a plan exists but no `crm_visits` row does, the saved-plan card reads
**"Visit not scheduled yet"**.

### Due-callback badge

One-page-per-stage removes today's behaviour where a qualified lead with an open
`follow_up_at` *also* appears in Follow-up as a reminder.

`follow_up_at` is retained on qualified leads and surfaced as a **due-callback badge
on the Qualified page**. Same information, one home.

## Migration

One-time, idempotent, additive to `backend/app/migrations.py` so it applies on next
boot. Ordered so each statement's `WHERE` is disjoint from the others' effects.

```sql
-- 1. the 159 qualified leads (contacted + visit_planned)
UPDATE leads SET stage = 'qualified' WHERE stage IN ('contacted', 'visit_planned');

-- 2. new-stage leads with an open callback, split by whether we ever reached them.
--    Without this they would wrongly land back on New — they are in Follow-up today.
UPDATE leads SET stage = 'call_not_received'
 WHERE stage = 'new' AND follow_up_at IS NOT NULL AND NOT ever_connected;

UPDATE leads SET stage = 'follow_up'
 WHERE stage = 'new' AND follow_up_at IS NOT NULL AND ever_connected;

-- 3. retire stages that hold no leads but are referenced in code
UPDATE leads SET stage = 'rejected' WHERE stage IN ('lost', 'future_prospect', 'timepass');
```

`new`, `visit_scheduled`, `rejected` and `rnr` are untouched.

Idempotent: after one run no row matches any `WHERE`, so re-running on every boot is a
no-op — the same property the existing back-fills in that file rely on.

### Dry run

Read-only, run before migrating to see the real split:

```sql
SELECT stage,
       count(*) FILTER (WHERE follow_up_at IS NOT NULL AND NOT ever_connected) AS to_cnr,
       count(*) FILTER (WHERE follow_up_at IS NOT NULL AND ever_connected)     AS to_followup,
       count(*)                                                                AS total
FROM leads GROUP BY stage ORDER BY total DESC;
```

### Standalone script

`backend/scripts/migrate_stages.sql` — the same statements wrapped in a transaction
with before/after counts, for running by hand against Neon.

## Files affected

**Backend**
- `app/routers/leads.py` — `SEGMENTS` becomes stage equality; `_TERMINAL` shrinks;
  `confirm_lead`, `call_result`, `set_followup`, `reject_lead` set stage explicitly;
  the visit-plan endpoint stops writing stage; new `call_not_received` segment.
- `app/routers/metrics.py` — dashboard counts read stage instead of
  `confirmed`/`qualified_at`.
- `app/migrations.py` — the migration above.
- `app/routers/visits.py` — booking still sets `visit_scheduled`; terminal-stage guard
  list updated.

**Frontend**
- `src/lib/leads.ts` — `LEAD_SEGMENTS`, `STAGE_LABEL`, `STAGE_CLASS`.
- `src/components/Sidebar.tsx` — nav items: add Call Not Received, remove RNR.
- `src/main.tsx` — routes: add `/leads/call-not-received`, redirect `/leads/rnr`.
- `src/pages/Rnr.tsx` — folded into the Rejected page.
- `src/pages/LeadDetail.tsx` — saved-plan card copy.
- `src/pages/Analytics.tsx` — stage references.

## Testing

- Unit: stage transition for each row of the transitions table, asserting the exact
  resulting stage (pure helpers where possible; the SQL branches via the existing
  `MISS_REASONS` tests).
- Migration: assert the four statements are disjoint and idempotent — running twice
  yields the same counts as running once.
- Assert every stage in the model maps to exactly one page, and every page's predicate
  references only stages in the model, so a lead can never be orphaned again.

## Risks

- **Irreversible without a backup.** The migration overwrites `stage` for ~159+ rows
  with no record of the prior value. Snapshot `leads` (or at least `id, stage`) before
  running.
- **The `new` split depends on `ever_connected` being accurate.** It is set only by a
  connected call result; leads worked before that flag existed would be classed as
  `call_not_received`. Acceptable — they get called either way.
- Pages and stages must be changed together; a partial deploy strands leads on a page
  whose predicate no longer matches.
