# Direct Demand portal — change specification

**Version:** 1.0
**Date:** 10 September 2026
**Owner:** Akshit Chaudhary
**Delivery lead:** Rajnish (Direct Demand)
**Audience:** the engineer(s) building this, the product manager running it, and the Direct Demand team who will live with it
**System:** `directdemand.vercel.app` (React + Vite frontend on Vercel) and `direct-demand-api-7k48.onrender.com` (FastAPI on Render), Neon Postgres `direct demand portal`
**Source of these changes:** working session between Akshit and Rajnish on 7 September, walking the portal screen by screen alongside the Demand CRM, plus the funnel diagnosis of 5–7 September

---

## 0. Read this first

**This is a live production system.** Five relationship managers, one test account and ten admins use it every working day. There are 3,747 leads in it, 260 visit records and an auto-dialer that runs against live lead data. A bad release does not cause an outage, it causes five people to lose a day of selling and, in the worst case, silently loses the record of which buyer belongs to whom.

**Everything in this document is written to be built.** Where I am not certain, I have said so in a `DOUBT` box rather than guessed, because a confident wrong instruction is more expensive than a question. Do not build anything sitting under an unanswered `DOUBT` without getting the answer first.

### Conventions used here

| Marker | Meaning |
|---|---|
| **MUST** | Required for the change to be considered done |
| **SHOULD** | Strongly recommended; deviate only with a reason recorded |
| **DOUBT-n** | An open question. The answer changes what gets built. Do not proceed on that item until answered |
| **CAREFUL-n** | A production risk the product manager must actively manage. Not optional reading |
| **OUT** | Explicitly not in this scope |

### Confidence grouping

Changes are grouped by how confident I am, not by priority:

- **Group A — specified and safe.** Build these. Behaviour and blast radius are known.
- **Group B — specified but blocked on a decision.** The engineering is clear; a product decision is not. Each carries a `DOUBT`.
- **Group C — not understood.** Recorded so nothing is silently dropped. Not buildable as written.

---

## 1. Current state of the system

All figures pulled from the production database on **10 September 2026 at 11:24 IST**. They will drift; re-check before a migration.

### 1.1 Lead stages

`leads.stage` is the single source of truth for which page a lead appears on. From `backend/app/routers/leads.py`:

```python
STAGES = ("new", "call_not_received", "follow_up", "qualified",
          "visit_scheduled", "revisit_scheduled", "won", "rejected", "rnr")

_TERMINAL = "('won','rejected','rnr')"   # stages a lead never leaves on its own

SEGMENTS = {
    "new":               "stage = 'new'",
    "call_not_received": "stage = 'call_not_received'",
    "followup":          "stage = 'follow_up'",
    "qualified":         "stage = 'qualified'",
    "pipeline":          "stage = 'visit_scheduled'",
    "revisit":           "stage = 'revisit_scheduled'",
    "converted":         "stage = 'won'",
    "rejected":          "stage IN ('rejected','rnr')",
}
```

The code carries this comment, which is a design decision worth preserving:

> `stage` is authoritative: every page is a plain equality on it, so a lead lives on exactly one page and can never fall between them.

Current distribution:

| Stage | Leads |
|---|---:|
| call_not_received | 1,537 |
| rejected | 1,187 |
| qualified | 443 |
| follow_up | 376 |
| rnr | 119 |
| visit_scheduled | 81 |
| revisit_scheduled | 4 |
| new | 0 |
| won | 0 |
| **Total** | **3,747** |

`won` exists in the code and has never been used. No lead has ever been marked as sold in this portal.

### 1.2 Rejection reasons

Across the 1,306 leads in `rejected` and `rnr`:

| reject_reason | Leads |
|---|---:|
| Requirement Mismatch | 951 |
| No Requirement | 229 |
| RNR | 116 |
| Invalid Number | 7 |
| (blank) | 3 |

"Requirement Mismatch" is a catch-all. Reading the free-text `reject_notes` behind it, roughly 45% are "not interested", 12% are brokers, 8% are a genuine budget gap, and the rest are scattered. **It cannot be split mechanically.** See CH-06.

### 1.3 Visits

`crm_visits` holds 260 rows across 88 leads. 41 leads have at least one completed visit.

| status | Rows |
|---|---:|
| completed | 128 |
| upcoming | 80 |
| cancelled | 52 |

`buyer_feedback` is filled on **0 of 260** rows. `sales_feedback` is filled on 75.

**Critical implementation fact.** From the model docstring in `backend/app/models.py`:

> `visit_id` is the Core visit number returned by the booking API and is the join key into the ops visits sheet, from which `status` (upcoming | completed | cancelled) and the feedback fields are synced.

That is, **`status`, `visit_date`, `buyer_feedback` and `sales_feedback` are currently written by a sync from a Google Sheet, not by the portal.** Any change that lets the portal write those fields creates two writers for the same column. This is the single largest technical risk in this document. See CH-08 and CAREFUL-04.

### 1.4 Inventory

`inventory_units` holds 221 rows, synced from the Acquired Property sheet.

| status | Units |
|---|---:|
| Available | 176 |
| Ready | 17 |
| Booked | 27 |
| Dead | 1 |

### 1.5 Users

10 admin, 5 rm, 1 test_rm, all active.

### 1.6 What touches `stage`

Changing the stage list is not a local change. `stage` is referenced in:

- **Backend (12 files):** `routers/leads.py`, `routers/reports.py`, `routers/rm_summary.py`, `routers/huvo.py`, `routers/huvo_calls.py`, `routers/live_calls.py`, `routers/visits.py`, `routers/dialer.py`, `services/dialer.py`, `services/activity.py`, `services/matching.py`, `services/supply.py`
- **Frontend (12 files):** `main.tsx`, `MobileApp.tsx`, `components/Sidebar.tsx`, `components/Topbar.tsx`, `components/HuvoCallCard.tsx`, `lib/api.ts`, `lib/leads.ts`, `lib/report.ts`, `pages/LeadsSegment.tsx`, `pages/Reports.tsx`, `pages/Followup.tsx`, `styles/app.css`
- **The auto-dialer.** `stage` is a whitelisted targetable field in campaign rules (`backend/app/services/dialer.py:53`). A campaign built on `stage IN (...)` will silently change who it calls if a stage is renamed or a lead is migrated.

> **CAREFUL-01 — the auto-dialer.** Before any stage rename or migration, list every saved campaign and check its rule tree for `stage` conditions. A campaign that suddenly matches 951 migrated leads will start dialling them. There are 8 campaigns in `dial_campaigns`; check each, and pause any that are not `done` before the migration window.

### 1.7 How migrations work here

- `backend/app/migrations.py` runs at **every boot** and is **additive only** (`ADD COLUMN IF NOT EXISTS`). New columns go here.
- Anything that changes existing rows goes in `backend/scripts/*.sql` and is run **by hand** against Neon.
- There is a precedent to copy exactly: `backend/scripts/migrate_stages.sql`. It creates a backup table before overwriting, wraps the work in `BEGIN`, prints before-and-after counts, and is idempotent so a second run changes nothing. It also documents its own rollback:

```sql
CREATE TABLE IF NOT EXISTS leads_stage_backup AS SELECT id, stage FROM leads;
-- restore:  UPDATE leads l SET stage = b.stage
--           FROM leads_stage_backup b WHERE b.id = l.id;
```

**Every data-changing script in this document MUST follow that template.**

---

## 2. The target model

### 2.1 Three top-level buckets

Today the RM clicks between many separate lists. The decision on 7 September was to collapse these into three, with everything else becoming a filter inside them.

```
ACTIVE                      leads we are still working
├── New Leads               not yet qualified
│   └── filters: ringing / call not received / callback again
├── Qualified               requirement captured, working toward a visit
└── Visits
    ├── New visit           first visit to a property
    ├── Revisit             the SAME property seen again
    ├── Cancelled           booked, did not happen
    └── Negotiation         a price conversation with a number on the table

INACTIVE                    leads we have stopped working
├── Not interested          the buyer said no
├── Rejected                we stopped it (budget or requirement we cannot serve)
└── Bad lead                junk: wrong number, broker, mistaken enquiry

FUTURE PROSPECT             real buyers we cannot serve today
├── High intent             actively looking AND actively visiting; range known
└── Low intent              vague interest, no activity behind it
```

### 2.2 Definitions the team agreed, verbatim in meaning

- **Revisit** means the *same property* visited again by the same buyer. A buyer who sees DNS Newtown Heights and then Signature has made **two visits, not a revisit**. Revisit is the highest-intent bucket in the system and the rule set in the meeting was: *clear this bucket first, always*.
- **High intent (future prospect)** means the buyer is actively looking *and* actively doing property visits in the market, and we know his range. These go into a weekly session between Rajnish and the supply pipeline team, to be matched against homes being acquired.
- **Low intent (future prospect)** means someone who said "tell me if you have something at fifty lakh" with nothing behind it.
- **Bad lead** is kept separate from **Not interested** and **Rejected** on purpose, because bad leads are the feedback signal sent back to Meta. If all three are merged we cannot tell Meta which audience to stop sending.

> **CAREFUL-02 — do not merge the three inactive buckets to save effort.** The whole point of the split is the Meta feedback loop. A single "dead" bucket costs nothing to build and destroys the reason the change was requested.

### 2.3 Mapping from today's stages

| Today | Goes to | Notes |
|---|---|---|
| new | Active → New Leads | 0 rows today |
| call_not_received | Active → New Leads (filter) | 1,537 rows |
| follow_up | Active → New Leads (filter) | 376 rows |
| rnr | Active → New Leads (filter), or Inactive | See DOUBT-03 |
| qualified | Active → Qualified | 443 rows |
| visit_scheduled | Active → Visits → New visit | 81 rows |
| revisit_scheduled | Active → Visits → Revisit | 4 rows |
| rejected | Inactive, split three ways | 1,187 rows, see CH-06 |
| won | (unused) | Keep; it is the sale stage and will be needed |
| — | Active → Visits → Negotiation | New, does not exist |
| — | Future Prospect → High / Low | New, does not exist |

---

## 3. Group A — specified and safe. Build these.

### CH-01 · Hide Booked and Dead homes from matching and shortlists

**Problem.** The matching engine offers every unit in `inventory_units` regardless of status, including homes that are already sold. 26 visit cards currently point at Booked homes. RMs are taking buyers to flats that are no longer available.

**Where.** `backend/app/services/matching.py`, function `_inventory_units()` (around line 242). The query today is:

```sql
SELECT id, name, society, locality, city, configuration, area_sqft,
       price_text, price_lacs, status, image_url FROM inventory_units
```

There is no `WHERE` clause. `status` is selected only so it can be displayed downstream (around line 330); it is never filtered on.

**The precedent to mirror.** The supply half of the same file already does this correctly. `backend/app/services/supply.py:18` defines a hide-list:

```python
SUPPLY_STATUS_HIDE = [
    "Duplicacy", "Dead - Sold", "OH Rejected", "Dead - Not Interested",
    "Visit Cancelled", "Seller Rejected", "Cancelled Post Token", "Dead - Legal",
]
```

and `matching.py:274` applies it with `WHERE s.supply_status <> ALL(:hide)`.

**What to build.**

1. **MUST** add a module-level constant next to the existing one, e.g. `INVENTORY_STATUS_SHOW = ("Available", "Ready")`.
2. **MUST** apply it in `_inventory_units()`: `... FROM inventory_units WHERE status = ANY(:show)`.
3. **SHOULD** use a show-list rather than a hide-list, because a new status value appearing in the source sheet should default to hidden, not shown.

**Data impact.** 28 of 221 units disappear from suggestions (27 Booked, 1 Dead). No rows are written. Existing visit cards already pointing at Booked units are **not** touched by this change; see CH-02.

**Rollback.** Remove the `WHERE`. No data to restore.

**Acceptance.** A lead whose city and budget match a Booked unit no longer sees it in suggested properties. A unit flipped from Booked to Available in the source sheet reappears within one sync cycle.

> **CAREFUL-03 — tell the RMs the same morning.** Homes will visibly vanish from their shortlists. If nobody explains why, they will report it as a bug and lose confidence in the tool.

---

### CH-02 · Flag existing visit cards that point at unavailable homes

**Problem.** CH-01 stops new bad shortlists. It does not clean up the 26 cards already booked against Booked homes, some created in September.

**What to build.**

1. **MUST** show a warning badge on any `crm_visits` row in `upcoming` whose `home_id` maps to a unit now `Booked` or `Dead`.
2. **MUST NOT** auto-cancel these. A booked unit sometimes falls through and the visit may still be wanted.
3. **SHOULD** surface the list once to Rajnish so he can decide each one.

**Data impact.** Read-only.

---

### CH-03 · Lead detail becomes a popup, not a page

**Problem.** Opening a lead redirects to its own page and getting back to the list is awkward. This was raised directly in the session.

**What to build.** **MUST** open the lead in an overlay above the current list, closing back to the same scroll position and the same filters. The Demand CRM's channel-partner view is the reference pattern: clicking a row opens everything over the list.

**Where.** `frontend/src/pages/LeadDetail.tsx` and whichever list components link to it (`pages/LeadsSegment.tsx`, `pages/NewLeads.tsx`, `pages/Followup.tsx`).

**Data impact.** None. Frontend only, fully reversible.

> **CAREFUL-05 — keep a deep link.** Some people share lead URLs. The popup must still be reachable by a direct URL, or that habit breaks silently.

---

### CH-04 · The lead popup shows the full history in one place

**Problem.** Today the popup shows basic information and notes, notes appear outside the lead, and notes written at different stages do not read as one story. You cannot see what has happened to a buyer end to end.

**What to build.** One chronological timeline on the popup, merging:

1. **MUST** — stage changes with who made them and when (`activity_log`, `action='stage_change'`)
2. **MUST** — every reassignment, with the previous owner (`activity_log`, `action='assigned'`, which stores the old value)
3. **MUST** — all notes (`lead_notes`), regardless of the stage they were written in
4. **MUST** — calls, with outcome and duration (`call_logs`), and the recording where one exists
5. **MUST** — AI calls and their outcome (`huvo_call_updates`)
6. **MUST** — WhatsApp messages both ways (`wa_messages`, matched on last 10 digits of the phone)
7. **MUST** — visits with status and feedback (`crm_visits`)
8. **SHOULD** — a scheduled follow-up control, upcoming visits, a call button, preferred societies and recommended properties, all on the same popup

**Data impact.** Read-only. All of this data already exists; it is only unjoined.

---

### CH-05 · Property information on the lead and the shortlist

**What to build.** On a suggested or shortlisted property, **MUST** show: visits already done on that property, the property manager's name, price, days listed, price revisions, and the demand team's remarks. The property manager's name currently only appears when a visit is booked.

**MUST NOT** show channel-partner demand leads anywhere in this portal. Explicitly agreed as not relevant to this team.

**Data impact.** Read-only.

> **DOUBT-01 — social proof count.** The session asked to show how many visits have already happened, so an RM can say "46 visits have already happened at Gaur City 6" and even send a screenshot. **Is that count for the specific unit or the whole society, and does it include channel-partner visits?** I have assumed society-level and yes to CP visits, because that is the bigger and more persuasive number, but I have not built on that assumption. **Please confirm.**

---

### CH-07 · Make manual lead creation work, and add it from WhatsApp

**Problem.** The "Add lead" form exists and does not work. This matters because direct calls arrive from YouTube, from the website and from people who simply ring the office, and there is no way to capture them.

**What to build.**

1. **MUST** fix the existing manual create-lead form.
2. **MUST** add "create a lead" from a WhatsApp thread. The Demand CRM already has this flow; copy it, including the field order used there: city, then society, then number.
3. **MUST** make lead creation reachable from the top of every screen, not buried.
4. **SHOULD** default `source` to a value that identifies how it came in, so these do not pollute the Meta and portal source analysis.

> **DOUBT-02 — source values for manual leads.** Today `leads.source` holds `meta`, `99acres`, `magicbricks`, `whatsapp`. A manually created lead needs its own value or the source-performance reporting becomes wrong. **What should a phone walk-in and a YouTube enquiry be called?** I suggest `inbound_call`, `youtube`, `website` and `referral`, but this is your naming decision and it is hard to change later.

---

### CH-09 · Add "Book another visit" on a lead that has already visited

**What to build.** **MUST** add an action on a visited lead to book the next visit. Today there is no way to do this from a visited lead, which is part of why only 2 of 41 buyers who visited were ever given another appointment.

Whether the new visit is classified as a revisit or a new visit is determined by CH-11.

---

### CH-10 · Cancelled becomes a visible sub-bucket under Visits

**What to build.** **MUST** expose `crm_visits.status = 'cancelled'` as its own list. 52 rows already carry this status; this is a display grouping only, no data change.

**Why it matters.** 80 cards sit in `upcoming` with dates that have already passed. They are not pipeline, they were never closed off, and they make the funnel read larger than it is.

---

### CH-14 · Brochure in the property API, and a sendable inventory snapshot

**Problem.** To send a buyer a brochure, an RM has to leave the portal and open the mobile app.

**What to build.**

1. **MUST** add the brochure to the property API. The video API already exists and is used by Studio; only the brochure is missing.
2. **MUST** let an RM generate an inventory snapshot from the portal and send it to a buyer.
3. **SHOULD** make the live inventory screen the place this happens. It exists and is not being used today.

**Data impact.** Additive.

---

## 4. Group B — specified, but blocked on a decision

Do not start these until the `DOUBT` is answered.

### CH-06 · Split Inactive into Not interested, Rejected and Bad lead

**What to build.** Three separate states replacing today's single `rejected`, plus the existing `rnr`.

**The problem is the existing 1,187 rows.** 951 of them say "Requirement Mismatch", which reading the notes is roughly 45% not interested, 12% brokers, 8% budget, and the rest scattered. There is no rule that splits them correctly.

Three options:

| Option | What happens to history | Risk |
|---|---|---|
| **A. Legacy bucket** | All 1,187 move to a single `inactive_legacy` state. New rejections use the three new states. | Lowest. Nothing is misclassified. History stays queryable but coarse. |
| **B. One-time classification** | Run a keyword pass over `reject_notes` to split them. | Highest. Roughly a quarter would land in the wrong bucket, and the Meta feedback loop would be fed wrong data, which is the exact thing this change exists to fix. |
| **C. Re-tag on touch** | Leave history alone. The team re-tags a lead the next time they open it. | Medium. Slow, but never wrong. |

> **DOUBT-03 — which option, and what happens to `rnr`?** My recommendation is **A**, plus **C** running quietly behind it. I would not do B. Separately: **does `rnr` (119 leads, never reached after repeated attempts) belong in Active as a filter, or in Inactive as its own thing?** It is currently shown on the Rejected page (`SEGMENTS["rejected"] = "stage IN ('rejected','rnr')"`) but it is not a rejection, it is an unreachable buyer, and some of them are still worth calling. **Please decide.**

> **CAREFUL-06 — this migration is irreversible without the backup.** Follow the `migrate_stages.sql` template exactly: create `leads_stage_backup_v2` first, wrap in `BEGIN`, print before-and-after counts, make it idempotent. Do it in a low-traffic window with the team told in advance.

---

### CH-11 · Enforce the revisit definition

**Problem.** The agreed definition is that a revisit is the *same property* seen again. The portal today advances a lead to `revisit_scheduled` on any *second booking*, regardless of which property. The code and the definition disagree.

**What to build.** **MUST** classify a visit as a revisit only when `home_id` matches a previous completed visit for the same lead. Otherwise it is a new visit.

**Data impact.** Only 4 leads sit in `revisit_scheduled`, so the blast radius is tiny.

> **DOUBT-04 — historical rows.** Do we re-derive those 4 leads under the new rule, or leave them alone? Re-deriving is cleaner and the risk is negligible at this size, but it is your call.

---

### CH-12 · Add Negotiation as a tracked step

**Problem.** In 3,747 leads there is exactly one note mentioning a price conversation. There is no negotiation stage, table or route in this portal. It has never been tracked for a direct buyer, and it is the step immediately before a sale.

**The reference implementation already exists.** The Demand CRM has this properly: a `negotiation` stage that requires a `negotiation_date`, which then auto-advances to `after_negotiation_fu` once the date passes (`backend/api/main.py:654`, `backend/migrations/007_negotiation_date.sql`). Revisit works the same way with a required `revisit_date`.

**What to build.**

1. **MUST** record, for each negotiation: the date, who attended, what the buyer asked for, what we offered, and the outcome.
2. **MUST** make it visible as a sub-bucket under Visits.
3. **SHOULD** copy the Demand CRM's auto-advance behaviour so a negotiation date that passes moves the lead on by itself.

> **DOUBT-05 — stage or event?** Two implementations are defensible and they are not equally risky.
>
> **(a) A new `stage` value.** Consistent with this portal's "one page per stage" design. But it adds a tenth stage to a tuple referenced in 24 files and in the dialer's targetable field list.
>
> **(b) A separate `negotiations` table** keyed on lead, in the shape of the Demand CRM's `followups`. Leaves `stage` untouched, and lets a lead have several negotiations over time, which does happen.
>
> I lean to **(b)** because it is additive and does not touch the stage model, and because a buyer can genuinely negotiate more than once. **Please decide before anyone starts.**

---

### CH-08 · Visit completion and outcome from the portal

**Problem.** Completion can only be done in the app today. This is a large part of why 80 cards sit open past their date and why status arrives late. And `buyer_feedback` is empty on all 260 visits, while the Demand CRM captures its equivalent on 88% of channel-partner visits.

**What to build.**

1. **MUST** allow a visit to be marked complete from the portal.
2. **MUST** require a structured outcome before a visit card can be closed: an outcome (hot / needs another option / dead) plus one line of why.
3. **MUST** build a visit-completed API so the app and portal stay in step.

> **CAREFUL-04 — this column already has a writer. Read this before touching it.**
> `crm_visits.status`, `visit_date`, `buyer_feedback` and `sales_feedback` are **currently written by a sync from the ops Google Sheet** (`backend/app/services/visits_sync.py`; see the model docstring in `models.py`). If the portal starts writing the same columns, you have two writers and the sheet will overwrite whatever the RM typed, silently, on the next sync.
>
> Options, in the order I would consider them:
> 1. Write portal outcomes to **new columns** the sheet sync does not touch, and treat the sheet as authoritative only for `status`.
> 2. Make the sync **non-destructive**: `COALESCE(EXCLUDED.col, existing)` so the sheet can only fill a blank, never overwrite.
> 3. Retire the sheet as a writer entirely and make the portal authoritative.
>
> Option 3 is the right end state and the largest change. **Do not pick one without deciding what happens to the sheet.**

> **DOUBT-06 — OTP flow versus assisted flow.** The session decided to "take the OTP visit flow for now" and just capture completion and feedback. But a direct visit is an *accompanied* visit where an RM is present and no OTP may be issued at all. **Does the OTP completion path actually work when no OTP was generated?** If it does not, this decision needs revisiting. I could not confirm either way from the code and this needs someone who knows the Core visit API.

> **DOUBT-07 — enforce the required outcome from when?** If it is compulsory immediately, the 80 open cards cannot be closed until someone fills a field for visits that may have happened weeks ago. I recommend enforcing it on **new closures only** and leaving the backlog exempt, but say if you want it on everything.

---

### CH-13 · Future Prospect bucket with High and Low intent

**What to build.** A two-state bucket for real buyers we cannot serve today, with the society they want captured against them, feeding a weekly review with the supply pipeline team.

> **DOUBT-08 — who applies the definition, and how?** "Actively looking and actively visiting the market" is clear on paper and subjective in practice. If every RM applies it differently, Future Prospect becomes another dumping ground, which is exactly what Rejected became. Options: a short checklist on the form, or only a team lead can move a lead here. **Which?**

> **DOUBT-09 — where does the society come from?** To match a future prospect against incoming supply, we need the society or micro-market stored against the lead in a structured field. `lead_confirmed_data.shortlisted_societies` exists as JSONB but is abused: 83 leads have more than ten societies listed, one has 130, which makes matching meaningless. **Do we cap the selection at three ranked choices?** I recommend yes, and that the cap is enforced on the form.

---

### CH-15 · WhatsApp as a real inbox

**Problem.** WhatsApp is a button on a screen. 765 people have messaged us; roughly one in ten ever got a reply. The requirement stated in the session was blunt: *there should not be a missing message.*

**What to build.**

1. **MUST** a proper inbox with unread state and notifications that keep surfacing until answered.
2. **MUST** an escalation when a message goes unanswered.
3. **MUST** create-a-lead from a thread (also covered in CH-07).

> **DOUBT-10 — the escalation.** Agreed in principle: if there is no reply within two hours, an email goes out. Unspecified: **who receives it, does it fire per message or per thread, and is there a cap?** At current inbound volume, per-message escalation could be 30 to 50 emails a day, which people will filter away within a week and then the control is worthless. I recommend: per thread, once, to the assigned owner, with a copy to Rajnish, suppressed outside working hours. **Confirm.**

---

### CH-16 · Turn WhatsApp auto-assignment back on

**Problem.** New WhatsApp conversations sit unowned until somebody manually picks an owner.

**The logic already exists and is good.** From `backend/app/services/wa_assign.py`:

> Nothing here runs automatically any more. An inbound message used to assign the thread on arrival; it doesn't — a new conversation stays unowned until someone chooses an owner.

The rules, in order: if the number already has a lead with an owner it goes to that same RM; otherwise the active RM with the fewest open conversations; ties to whoever was assigned longest ago. Contacts tagged `rejected` are never assigned. That first rule is the important one and it is the reason not to replace this with plain round-robin.

**What to build.** **MUST** re-enable assignment on inbound. This is a switch, not a rewrite.

**Data impact.** Only 7 of 655 contacts are currently unassigned, so switching this on is not a bulk dump.

> **DOUBT-11 — why was it switched off?** The comment says it was deliberate. Somebody disabled this on purpose and neither I nor this document knows what went wrong. **Find out before re-enabling.** If it was disabled because RMs were being handed conversations they could not service, re-enabling it without fixing that will recreate the problem.

---

### CH-17 · Five attempts before a lead can be marked dead

**Problem.** Of the leads we ever dialled, most got exactly one call. Our own answer rate is roughly the same on the second, third and fourth attempt as on the first, so every attempt not made throws away a real chance of reaching the buyer.

**What to build.** **MUST** block marking a lead dead before five logged attempts across the first seven days.

**It must interact with what already exists.** `backend/app/routers/leads.py` already has a miss-handling rule: five consecutive missed calls (`miss_count`) or eight lifetime (`miss_total`) auto-moves a lead to `rnr`, with the reason "Auto-RNR — 5 consecutive or 8 total missed calls". Retry gaps are set from `MISS_REASONS` (Did Not Pick +3h, Switched Off +6h, and so on). **Do not build a second, parallel rule.** Extend this one.

> **DOUBT-12 — the exception list.** A hard block is wrong for cases where one call is genuinely enough. My proposed carve-outs, where a lead may be closed immediately: **wrong or invalid number; the caller is a broker; the buyer explicitly says no on the call; the person is a seller, not a buyer; the buyer has already purchased elsewhere.** **Confirm this list, add or remove.** Everything not on it needs five attempts.

---

### CH-18 · Trim the RM view; admins keep everything

**What to build.** **MUST** show the RM only the three buckets and the funnel. Admins keep every screen.

> **DOUBT-13 — the exact keep list.** RMs today can reach: New Leads, Follow-up, lead segments, Dialer, Live Calls, Call Log, Inventory, Supply, Chat, Huvo Calls, Reports, Analytics, Logs, Settings. **Tell me which of these an RM keeps** and I will hide the rest behind the role check. My guess at the keep list is: the three buckets, the funnel dashboard, Inventory, Chat, Live Calls and Call Log. I am least sure about Supply and Huvo Calls.

> **CAREFUL-07 — hiding a screen someone depends on.** If an RM is mid-workflow on a screen that disappears, they will work around it in a spreadsheet, which is where this team already went once. Ask the five RMs which screens they actually open before hiding anything.

---

### CH-19 · The dashboard becomes a funnel

**Problem.** The current dashboard is analytics. The requirement stated was: nothing fancy, simple and basic, a structure every person on the team understands at a glance.

**What to build.**

1. **MUST** show the funnel by stage, counted in **unique buyers, not visit rows**. This was decided on 5 September and it matters: 260 visit cards belong to only 88 buyers.
2. **MUST** show targets alongside actuals, for example 20 of 45.
3. **MUST** be one overall funnel, filterable to a person, rather than a separate view per person.
4. **SHOULD** move analytics out into its own screen later.

> **DOUBT-14 — where do targets come from?** Hardcoded, per-user settings, or a config screen. And are they per person per month, resetting on the first? Without a source of truth the funnel shows a number nobody can change. I recommend a small admin-editable table, per user per month.

> **DOUBT-15 — where does the target appear?** The session said both "put the target in one place" and "show it everywhere so the number left today stays in their head". **Which?** I recommend the funnel as the source of truth and a small persistent counter in the top bar.

---

### CH-20 · Cross-channel buyer view

**What to build.** On the lead popup, show whether this buyer has also visited with a channel partner.

**How the match works.** Last five digits of the mobile, plus name, plus society. Both participants in the session acknowledged the accuracy is low.

> **CAREFUL-08 — false positives are dangerous here.** If an RM sees "this buyer is already with a broker" and it is wrong, they may back off a live buyer, or start a fight with a channel partner that costs us more than the lead was worth. **MUST** present this as a *possible* match with the basis shown, never as fact, and never auto-suppress a lead because of it.

> **DOUBT-16 — confirm the above is acceptable,** or tell me to leave this out of v1. I would rather ship it as an advisory chip than not at all, but it is a judgement call.

---

## 5. Group C — raised in the session, not understood

These were said and I could not reconstruct the intent from the recording. They are listed so nothing is silently dropped. **None of these are buildable as written.**

| ID | What was said, as I understood it | What I need |
|---|---|---|
| **C-01** | The booking widget has to stay at lead level, is separate, and something is usable "behind it in the page engine" | Which screen was on display, and what should change |
| **C-02** | "The map is going through the API" | Which map. The visit planner uses Google Maps. What was the decision |
| **C-03** | "AI support, we should understand this AI, and if it exists we will build it on the side" | Whether this is the Huvo AI caller, the AI RM summary, or something new |
| **C-04** | On new leads, "first they will have to say yes, then it goes inside" | What the yes step is and where it sits |
| **C-05** | "Preferred society, what is in the market, should the preferred recommendation come here" | Whether you want market data for the buyer's preferred society, or recommendations derived from it |
| **C-06** | "Stages, and inside this build that thing" immediately before the create-lead point | The first half of the sentence |

I have treated the scheduling conversation near the end of the session as not actionable. **If anything in there was a work item, tell me.**

---

## 6. Release plan

### 6.1 Sequencing

Ship in this order. Each release is independently useful and independently reversible.

| Release | Contents | Data changes | Risk |
|---|---|---|---|
| **R1** | CH-01, CH-02, CH-03 | None | Low |
| **R2** | CH-04, CH-05, CH-07, CH-09, CH-10, CH-14 | Additive columns only | Low |
| **R3** | CH-08, CH-12 | New columns or table | Medium. Depends on DOUBT-05, 06, 07 and CAREFUL-04 |
| **R4** | CH-06, CH-11, CH-13, CH-18, CH-19 | **Stage migration** | **High** |
| **R5** | CH-15, CH-16, CH-17, CH-20 | Behavioural | Medium |

**R4 is the dangerous one.** It changes the stage model, migrates 1,187 rows and removes screens from five people on the same day.

### 6.2 Rules for R4

1. **MUST** take a stage snapshot into a backup table first, following `migrate_stages.sql` exactly.
2. **MUST** check every auto-dialer campaign for `stage` conditions and pause anything not `done` (CAREFUL-01).
3. **MUST** ship the bucket restructure in **one release**, not drip-fed. A half-migrated bucket structure is worse than either state.
4. **MUST** tell the team the evening before, with a one-page note showing where each old list now lives.
5. **SHOULD** run it outside working hours. The team works roughly 10:30 to 18:30 IST, six days a week, so early morning is the window.
6. **SHOULD** keep the old segment routes alive as redirects for two weeks, so a bookmarked link does not 404.

### 6.3 Acceptance for the whole programme

The change is done when:

- An RM opens the portal and sees three buckets, not a long list.
- No suggested property is a Booked home.
- A visit cannot be closed without an outcome, and that outcome survives the next sheet sync.
- A negotiation is recorded with an attendee and an outcome on the day it happens.
- A lead marked dead has five logged attempts behind it, or falls under an agreed exception.
- The funnel shows unique buyers against target, and Rajnish uses it in the Monday review instead of a spreadsheet.

### 6.4 The measure that actually matters

> **CAREFUL-09 — the team is currently working in a Google Sheet, not the portal**, because the portal had too many issues. That is the real problem this rebuild has to solve. **Set a date on which the sheet is retired**, and make it a stated condition of R4. Otherwise the portal gets rebuilt and still is not used, which is how it got into this state.

---

## 7. Consolidated open questions

Everything the team is blocked on, in one place. Numbered for reply.

| # | Question | Blocks |
|---|---|---|
| DOUBT-01 | Social proof count: unit or society, and does it include CP visits? | CH-05 |
| DOUBT-02 | What `source` values do manually created leads get? | CH-07 |
| DOUBT-03 | Which migration option for the 1,187 rejected leads, and where does `rnr` belong? | CH-06 |
| DOUBT-04 | Re-derive the 4 historical revisit rows, or leave them? | CH-11 |
| DOUBT-05 | Negotiation as a stage or as a separate table? | CH-12 |
| DOUBT-06 | Does the OTP completion path work for an accompanied visit with no OTP? | CH-08 |
| DOUBT-07 | Enforce the required visit outcome on new closures only, or on the backlog too? | CH-08 |
| DOUBT-08 | Who may move a lead to Future Prospect, and against what checklist? | CH-13 |
| DOUBT-09 | Cap shortlisted societies at three ranked choices? | CH-13 |
| DOUBT-10 | WhatsApp escalation: recipient, per message or per thread, and a cap? | CH-15 |
| DOUBT-11 | Why was WhatsApp auto-assignment switched off? | CH-16 |
| DOUBT-12 | Confirm the exception list for closing a lead before five attempts | CH-17 |
| DOUBT-13 | Exact list of screens an RM keeps | CH-18 |
| DOUBT-14 | Where do funnel targets come from, and do they reset monthly? | CH-19 |
| DOUBT-15 | Target shown in one place or everywhere? | CH-19 |
| DOUBT-16 | Ship the cross-channel buyer chip in v1 as advisory, or leave it out? | CH-20 |
| C-01 to C-06 | Six items from the session I could not reconstruct | — |

---

## 8. Things deliberately not in this document

**OUT — call recordings.** All calls are recorded and uploading to the meetings app. The session explicitly parked this: fix the basic layout first, come back to recordings.

**OUT — analytics.** Moves to its own screen later. Not part of this work.

**OUT — the buyer promise, referral programme, micro-market pods and channel-partner referral rules.** These are business decisions from the wider plan, not portal changes.

**OUT — "qualified must have three matched homes."** This was my recommendation from the diagnosis, not a decision taken in the session. Roughly 175 of 443 qualified leads currently match no live home, so applying it as a hard gate would reclassify a large part of the pool overnight. If you want it, I would ship it first as a visible warning on the lead rather than a gate, and harden it only after seeing the effect. **Say if you want it added.**

---

## 9. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 10 Sep 2026 | First issue. Counts as of 10 Sep 11:24 IST. Code references verified against the repository on the same day. |
