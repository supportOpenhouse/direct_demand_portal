# WhatsApp template campaigns — design

**Status:** approved (rev 4), with rev 5 Gupshup corrections · **Date:** 29 Sep 2026, revised 1 Oct 2026 ·
**Approach:** A (campaign + recipient queue, sent by an in-process worker)

**Rev 2 changes:** templates are **stored and managed on our side** (§4.1, §9); new
**auto campaigns** that run periodically from a cron job (§7).
**Rev 4 (approved, 1 Oct):** UI split — a new **WhatsApp Campaigns** page for templates
and sending; **responses live on the existing WhatsApp page** behind a **Template
responses** toggle, with a red **+1** on a number that also has normal chat (§9).
**Rev 5 (1 Oct) — Gupshup corrections, from the docs-verified contract**
(`2026-10-01-gupshup-contract.md`, which wins wherever this spec differs): a send API 2xx means
**accepted by Gupshup**, not sent — a recipient goes queued → accepted → sent → delivered → read,
and most failures arrive later as callbacks; receipts match on `gsId` (then the WhatsApp id), not
`id`; button taps are attributed exactly through the reply's `context`; tiers and opt-out corrected
in §10; setup needs sent/delivered/read events switched on and payload version 2 (§15 notes).
**Rev 3 changes:** every campaign has its **own frozen list**, with **"repeat a previous
list"** as a source (§5.1); auto campaigns **repeat a list** instead of evaluating a rule,
re-sending to **everyone** or **only non-responders**, chosen per auto campaign (§7);
why Gupshup's Campaign Manager isn't used (§2.1); messaging tiers explained (§10).

## 1. Goal

Admins send an approved WhatsApp template to a list of **potential buyers** — numbers that
are usually *not* in `leads` yet — and **track every recipient's response**: whether the
message was sent, delivered and read, whether they replied, and what they said. Campaigns
run either **once** (launched by hand) or **automatically on a schedule**.

Tracking responses is the primary goal; sending is the means.

### Success criteria

1. An admin can build a campaign's own list from an upload, a pasted list, existing
   WhatsApp contacts, or a previous campaign's list, see exactly which rows are valid
   before anything is sent, and launch.
2. For every campaign the counts add up: `queued + sent + failed + skipped = recipients`,
   and each `sent` row moves through `delivered → read` as Gupshup reports it.
3. Every reply is visible (a) on the campaign page against the recipient who sent it and
   (b) in the normal WhatsApp thread, owned by the right RM.
4. Quick-reply button answers are counted per button ("Yes 41 · No 17").
5. A crash or deploy mid-send resumes where it stopped; nobody is messaged twice.
6. An auto campaign produces **exactly one run per scheduled slot**, never messages a
   number again inside its cooldown, and every run is an ordinary campaign with the same
   tracking.

## 2. Decisions already made

| Topic | Decision |
|---|---|
| Send scope | Bulk campaigns only (no per-chat template button in v1) |
| Sending app | A **separate Gupshup app/number** for templates. Its callback is live: `POST /v1/gupshup/template-webhook?token=` (built 29 Sep); inbound rows carry `wa_messages.source_app='template'` |
| Recipients | Potential buyers, not `leads` rows. **Every campaign has its own frozen list.** Sources: **CSV/Excel upload**, **pasted list**, **existing WhatsApp contacts who aren't leads**, **repeat a previous campaign's list**. No Google Sheet. |
| Templates | Approved in Gupshup, **with variables** (`{{1}}`…) and possibly quick-reply buttons. **Stored and managed on our side** (`wa_templates`, admin UI). Gupshup sync is out of scope. |
| Who launches | **Admins only** (manual and auto) |
| Ownership | Existing WhatsApp rules, plus one owner per phone number across template and inbound chat, in both directions (§6) |
| Approach | **A** — campaign + per-recipient queue, drained by an in-process loop |
| Reply attribution | A reply belongs to the **most recent campaign message sent to that number before the reply**. Button answers are matched exactly by message id. |
| Auto campaigns | A stored definition (template + seed list + schedule + repeat mode); a **Render cron** turns each due slot into an ordinary campaign run whose list repeats the previous run's (§7) |
| Sending path | Our app calls Gupshup's **Template Message API once per recipient** (§2.1); Gupshup's dashboard Campaign Manager is not used |

### 2.1 Why not Gupshup's Campaign Manager

Gupshup has two ways to send templates (checked against their docs, 1 Oct 2026):

| | Campaign Manager | Template Message API |
|---|---|---|
| What | A **dashboard** screen: upload CSV/XLS (`Phone` column), pick template, map variables, schedule | `POST /wa/api/v1/template/msg` |
| Recipients per call | a whole list (up to 1M) | **one** (`destination` is a single number) |
| Drivable by our app | **no public API documented** for creating/launching a campaign or uploading its list | yes; returns a `messageId` |
| Results | sent / delivered / read **totals in their dashboard** | per-message status on **our webhook**, keyed by `messageId` |

Campaign Manager would leave results in their dashboard, give us no `messageId`s (so a reply
could never be tied to a campaign or recipient — the primary goal), and bypass our
ownership, opt-out, cooldown and auto-repeat rules. So the app hands Gupshup one message per
recipient via the API and keeps the `messageId`; **Gupshup still does the delivery**. The
send loop (§5.2) is paced because of the daily messaging limit (§10).

## 3. Scope

**In:** template management (our table + admin UI), manual campaigns from 4 sources (incl. repeat a previous list), auto
campaigns on a schedule, paced sending from the template app, delivery/read tracking, reply
+ button-answer tracking, campaign list + detail pages, thread ownership, template bubble in
the chat thread, activity logging.

**Out (v1):** per-chat "send template" in the composer; media-header templates; one-off
scheduling of a manual campaign for a future time; A/B variants; syncing templates from
Gupshup; auto-creating leads from replies (the chat's "Create lead" does this).

## 4. Data model

Five new tables, created by the startup `create_all` (new tables need no `_ADD_COLUMNS`
entry). Phone keys follow the app-wide rule: **last 10 digits** (`phone10`).

### 4.1 `wa_templates` — ours, the source of truth

The approved template's content lives here. Gupshup only ever receives the template **id**
and the variable values; the body stored here is what the app previews, renders into the
chat thread and shows on the campaign page.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `gupshup_template_id` | TEXT NOT NULL, unique among **active** rows (partial index) | Gupshup's template UUID — the id its send API takes; not the template name, not Meta's numeric id (rev 5) |
| `name` | TEXT NOT NULL | e.g. `site_visit_followup` |
| `language` | TEXT NOT NULL DEFAULT `'en'` | |
| `category` | TEXT | MARKETING / UTILITY — informational |
| `body` | TEXT NOT NULL | the approved text with `{{1}}`… placeholders — **must match Gupshup's approved text exactly** |
| `variable_count` | INTEGER NOT NULL | derived from `body` on save; never typed |
| `variable_labels` | JSONB NOT NULL DEFAULT `'[]'` | a name per slot, e.g. `["Name","City"]` — drives column mapping |
| `variable_defaults` | JSONB NOT NULL DEFAULT `'[]'` | optional fallback per slot (e.g. `"there"` for a blank name); `null` = no fallback → row invalid |
| `buttons` | JSONB NOT NULL DEFAULT `'[]'` | quick-reply button texts, e.g. `["Yes","No"]` — buckets answers |
| `active` | BOOLEAN NOT NULL DEFAULT true | inactive = hidden from pickers, kept for history |
| `created_by` / `updated_by` | TEXT | admin emails |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

**Edits are guarded:** a template already used by a campaign can't have `body`,
`variable_count` or `gupshup_template_id` changed — past campaigns must keep rendering what
was actually sent. To change the text, deactivate it and add a new one — **it may reuse the
same Gupshup id**, since Gupshup lets an approved template be edited in place (rev 5: that's
why the id is unique only among active rows). `name`, labels, defaults and `active` stay
editable. Slots must run `{{1}}…{{n}}` with no gap and first appear in that order: Gupshup
fills `params` in the order the placeholders occur (rev 5).

### 4.2 `wa_campaigns` — one row per send (manual, or one auto run)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | TEXT NOT NULL | admin-chosen; an auto run is `"<auto name> · 2 Oct"` |
| `template_id` | UUID FK → `wa_templates.id` | |
| `source` | TEXT NOT NULL | `upload` \| `paste` \| `wa_contacts` \| `repeat` \| `auto` |
| `repeat_of` | UUID FK → `wa_campaigns.id`, nullable | the campaign whose list this one copied (`repeat` and `auto` runs) |
| `auto_campaign_id` | UUID FK → `wa_auto_campaigns.id`, nullable | set on auto runs |
| `run_slot` | DATE, nullable | the IST date an auto run is for; UNIQUE (`auto_campaign_id`, `run_slot`) — one run per slot, enforced by the DB |
| `status` | TEXT NOT NULL | `draft` → `sending` → `done`; `paused`; `cancelled` |
| `created_by` | TEXT NOT NULL | admin email, or `cron` for auto runs |
| `created_at`, `launched_at`, `finished_at` | TIMESTAMPTZ | |
| `send_window_start` / `_end` | TEXT DEFAULT `'10:00'` / `'19:00'` | IST wall-clock; nothing is sent outside it |
| `rate_per_minute` | INTEGER DEFAULT 30 | pacing (§5.2) |

Counts are **not stored** — computed from recipients, so they can't drift.

### 4.3 `wa_campaign_recipients` — one row per number per campaign

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `campaign_id` | UUID FK, indexed | |
| `phone10` | TEXT NOT NULL | UNIQUE (`campaign_id`, `phone10`) |
| `name` | TEXT | display only |
| `variables` | JSONB NOT NULL | values in slot order, e.g. `["Rahul","Noida"]` |
| `status` | TEXT NOT NULL | `queued` → `submitted` → `sent` → `delivered` → `read`; or `failed`, `skipped` |
| `skip_reason` | TEXT | `rejected_contact` \| `opted_out` \| `cooldown` \| … (kept, not dropped, so the list is auditable) |
| `error` | TEXT | Gupshup's rejection text for `failed` |
| `gupshup_id` | TEXT, indexed | provider message id — **ties receipts and button answers to this row** |
| `owner` | TEXT | RM who owns the thread at send time (§6) |
| `sent_at` | TIMESTAMPTZ | when Gupshup accepted it |
| `status_at` | TIMESTAMPTZ | last status change |

Index on (`phone10`, `sent_at`) — the cooldown and attribution queries both read "the last
campaign message to this number".

**Replies are not stored here.** They're in `wa_messages` (inbound rows from the webhooks)
and derived at read time (§8.3).

### 4.4 `wa_auto_campaigns` — the recurring definition (§7)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | TEXT NOT NULL | |
| `template_id` | UUID FK → `wa_templates.id` | |
| `seed_campaign_id` | UUID FK → `wa_campaigns.id` NOT NULL | the campaign whose list the FIRST run repeats; later runs repeat the previous run (§7.2) |
| `repeat_mode` | TEXT NOT NULL | `everyone` \| `non_responders` (§7.2) |
| `every_days` | INTEGER NOT NULL DEFAULT 1 | 1 = daily, 7 = weekly |
| `run_at` | TEXT NOT NULL DEFAULT `'11:00'` | IST time a slot becomes due |
| `next_slot` | DATE NOT NULL | the next IST date that is due |
| `cooldown_days` | INTEGER NOT NULL DEFAULT 7 | skip a number that a DIFFERENT campaign reached within this many days (its own repeats are governed by `every_days`) |
| `max_runs` | INTEGER, nullable | stop after this many runs; NULL = until deactivated or the list empties |
| `send_window_start` / `_end`, `rate_per_minute` | as on `wa_campaigns` | copied onto each run |
| `active` | BOOLEAN NOT NULL DEFAULT false | created paused; an admin turns it on |
| `created_by`, `created_at`, `updated_at` | | |

### 4.5 Existing tables

- **`wa_messages`:** each campaign send also writes an outbound row (`direction='out'`,
  `msg_type='template'`, `body` = the rendered text, `gupshup_id`, `author` = the
  launching admin or `cron`, `source_app='template'`). This is what puts it in the chat
  thread. Receipts already update this row by `gupshup_id`.
- **`wa_contacts`:** unchanged schema; ownership written here as today (§6). A new tag value
  `opted_out` (§10).

## 5. Manual campaigns

### 5.1 Build (draft)

```
template ──► source ──► normalise ──► validate ──► preview ──► save draft
```

1. **Pick a template** — its variable slots (with labels) define the columns needed.
2. **Pick a source:**
   - **Upload** — `.csv` or `.xlsx`, first sheet, header row. Parsed on the **server**
     (stdlib `csv`; `openpyxl` for `.xlsx` — a new backend dependency). The admin maps
     columns → phone + each slot. Name column optional.
   - **Paste** — one recipient per line: `phone, var1, var2…` (comma or tab).
   - **Existing WhatsApp contacts** — numbers in `wa_messages` with **no lead**, not
     `rejected` / `opted_out` (the set the bell's WhatsApp buckets show). Each slot is
     filled from a contact field (sender name from their last inbound message) or a fixed
     value typed once.
   - **Repeat a previous list** — pick an earlier campaign; its recipients (phone, name,
     variables) are copied as this campaign's own list (`repeat_of` records the source).
     Optional filter: **everyone** or **only those who didn't reply**. The copy is
     re-validated now — opted out, rejected, became a lead since, inside the cooldown —
     and may use a different template if the slot count matches (else variables are
     re-mapped like an upload).
3. **Normalise** each phone to `phone10` (existing `norm_phone` / `digits10`).
4. **Validate, row by row** — invalid phone · missing variable with no default · duplicate in
   this list → shown, not saved. `rejected` / `opted_out` / inside the cooldown → saved as
   `skipped` with the reason.
5. **Preview** — counts (`valid · invalid · duplicate · skipped`), the first few rendered
   messages exactly as recipients will see them, and a warning above the daily limit (§10).
6. **Save** → `status='draft'`, recipients `queued`. Nothing is sent yet.

### 5.2 Launch and send

- **Launch** sets `status='sending'`, `launched_at=now()`; logged `wa_campaign_launched`.
- **The send loop** runs in the RUN_SCHEDULER process next to the dialer
  (`services/wa_campaigns.py`: `start_campaign_sender()` / `stop_…()`, started in `main.py`'s
  lifespan). Every few seconds, for each `sending` campaign inside its IST window, it takes
  up to its per-tick share of `rate_per_minute` `queued` rows and for each:
  1. **claims** it: `UPDATE … SET status='submitted' WHERE id=:id AND status='queued'
     RETURNING …` — a row is never sent twice, even across a restart;
  2. **assigns the thread owner** (§6);
  3. **calls Gupshup's template API from the template app** (`POST /wa/api/v1/template/msg`
     with that app's `source` number, `src.name`, API key, and
     `template={"id": …, "params": [...]}`);
  4. on 2xx: stores `gupshup_id`, `sent_at`, `status='sent'`, writes the `wa_messages`
     outbound row; on rejection: `status='failed'`, `error` = Gupshup's text. One failure
     never stops the batch.
- No `queued` rows left → `status='done'`, `finished_at=now()`.
- **Pause / Resume / Cancel** flip `status`; the loop only reads `sending`.
- **Recovery:** a row stuck in `submitted` (crash between claim and Gupshup's answer) is
  **not** retried automatically — Gupshup may have sent it. It shows as "Unknown — check"
  with a manual Retry.

**New config** (template app): `GUPSHUP_TEMPLATE_API_KEY`, `GUPSHUP_TEMPLATE_SOURCE_NUMBER`,
`GUPSHUP_TEMPLATE_APP_NAME` (plus the existing `GUPSHUP_TEMPLATE_WEBHOOK_SECRET`). Sending
refuses with a clear "not configured" until all three are set.

## 6. Ownership

Uses `wa_assign` unchanged, applied **per recipient at send time**:

1. **The number already has a WhatsApp owner** (`wa_contacts.assigned_to`) → keep it.
2. **Else the number has a lead with an owner** → that RM.
3. **Else** → the active `rm` given the fewest conversations **today (IST)**, ties by longest
   since last assignment.
4. `rejected` / `opted_out` contacts are never sent to, so never assigned.

The recipient row records the `owner` chosen. **"And vice versa"** falls out of the key:
`wa_contacts` is keyed by `phone10`, so the template send and a later inbound from that
number are one thread with one owner, and converting that thread to a lead keeps the owner
(`_designated_rm` → `assign_if_unassigned` returns the existing one). A test pins it.

> ⚠️ Known gap, unchanged: the hourly lead sweep (`lead_assign`) doesn't consult
> `wa_contacts` (§13.3).

## 7. Auto campaigns

### 7.1 What it is

A stored definition — **template + seed list + schedule + repeat mode** — that produces one
ordinary campaign run per scheduled slot. Each run is a normal `wa_campaigns` row
(`source='auto'`, `repeat_of` = the run it copied), sent by the same loop and tracked on the
same detail page. The definition page lists its runs with their funnel numbers side by side.

### 7.2 Each run repeats a list

The first run copies the list of the **seed campaign** (any earlier manual campaign, e.g.
the one built from an upload). Every later run copies the **previous run's** list, so the
list carries forward run to run. `repeat_mode`, chosen per auto campaign:

- **`everyone`** — every number on the previous run's list, again.
- **`non_responders`** — only numbers that did **not** reply to the previous run (reply =
  §8.3's rule, or any button tap). The list shrinks run by run — a follow-up/nudge sequence.

Always removed when copying, whatever the mode: `opted_out`, `rejected`, numbers that have
**become a lead** since, numbers a **different** campaign reached within `cooldown_days`,
and numbers whose last send `failed` as not-on-WhatsApp. Variables are copied with each
row. When a run's list comes out empty, the auto campaign stops itself ("finished — no one
left to message"); likewise after `max_runs`.

### 7.3 The cron job

A new task in `scripts/20_cron_tasks.py`: **`wa_auto`**, calling
`services.wa_campaigns.run_auto_campaigns(trigger="cron")` directly (same shape as the
`visits` / `whatsapp` / `leads` tasks). Schedule the Render Cron Job every **15 minutes**.

Each invocation, for every `active` auto campaign whose `next_slot` + `run_at` (IST) is due:

1. **Insert the run** `wa_campaigns(auto_campaign_id, run_slot=next_slot, source='auto',
   repeat_of=<previous run or seed>, status='sending', created_by='cron', …)`. The UNIQUE
   (`auto_campaign_id`, `run_slot`) makes a second cron firing a no-op.
2. **Copy the list** from `repeat_of` per §7.2.
3. **Advance** `next_slot += every_days` — in the **same transaction** as 1–2.

If the previous run is **still sending** when the next slot comes due, that slot is skipped
(logged) rather than started — a run can't repeat a list that hasn't finished going out.

The cron **only creates and queues** the run; the in-process send loop sends it. So the cron
needs no Gupshup credentials, and the window / pacing / daily-limit rules apply identically.

**Missed slots** (cron down for two days) are not replayed: one run for the latest due slot,
then `next_slot` moves past today.

### 7.4 Turning it on

Created **inactive**. The page shows a **dry run** — "the next run would message 143
numbers" with the first rendered messages — and only then **Activate**. Pausing an auto
campaign stops future runs; a run already sending is paused separately like any campaign.

## 8. Response tracking (the point of the feature)

### 8.1 Delivery and read

The `message-event` handler (both webhooks) already updates `wa_messages.status` by
`gupshup_id`. It also runs, **forward only** (receipts can arrive out of order):

```sql
UPDATE wa_campaign_recipients
   SET status = :new, status_at = now()
 WHERE gupshup_id = :id AND rank(:new) > rank(status)
```

`failed` from Gupshup sets `failed` + `error` from the event payload.

### 8.2 Quick-reply button answers

A button tap arrives as an inbound message of a button type, carrying the button text and
the **id of the message answered**. Two changes:

1. **Webhook (`_text_of`):** render button replies as their text (today they're stored but
   blank in the thread).
2. **Attribution:** match that id to `wa_campaign_recipients.gupshup_id` — exact — and count
   answers per template button.

⚠️ Exact field names to confirm on the first real tap; the raw callback is in
`wa_messages.raw`, so a mismatch is a mapping fix, not data loss.

### 8.3 Replies

A recipient **replied** when `wa_messages` has an inbound row from their `phone10` with
`created_at > sent_at` and no later campaign message to that number before it (attribution
rule). Computed in the detail query. Shown per recipient: first reply text, time to first
reply, total replies.

### 8.4 What the admin sees

```
Campaign: Noida re-engage · template site_visit_followup · launched 29 Sep 11:02 by admin
Recipients 412 · skipped 14 · sent 391 · failed 7 · delivered 371 · read 300 · replied 58
Buttons: Yes 41 · No 17
```

## 9. UI

Two places:

- **A new page, `/wa-campaigns` — "WhatsApp Campaigns"** (admin-only, sidebar under WhatsApp):
  everything about templates and SENDING, as the three tabs below plus New campaign and
  Campaign detail.
- **The existing WhatsApp page (`/chat`)** — everything about RESPONSES (§9.1).

The new page's three tabs:

1. **Campaigns** — every run (manual + auto), name · template · source · status · launched ·
   funnel numbers.
2. **Auto campaigns** — definitions: name · template · schedule ("Every 3 days 11:00") ·
   repeat mode · next run · active toggle · last run's numbers. Create/edit form: seed
   campaign → template → repeat mode (everyone / non-responders) → schedule + cooldown +
   max runs → **Dry run** → Save (inactive) → Activate.
3. **Templates** — the `wa_templates` list with **Add / Edit / Deactivate**. Form: Gupshup
   template id, name, language, category, body (with a live "detected 2 variables" and a
   rendered preview), a label + optional default per slot, buttons. Locked fields (§4.1)
   are read-only once the template has been used.

Plus:
- **New campaign** (manual) — template → source → column mapping (upload) → validation +
  preview → name / window / rate → **Save draft** / **Launch**.
- **Campaign detail** — funnel as `.count-pill` boxes (**All · Sent · Delivered · Read ·
  Replied · No reply · Failed · Skipped**), button tallies, then a table: name · phone ·
  status · owner · first reply · replied at; a row opens the WhatsApp thread. Pause / Resume
  / Cancel in the topbar slot; CSV export; **Repeat this list** (opens New campaign with
  this list as the source) and **Make it automatic** (opens an auto campaign seeded with it).
- **Chat thread** — `msg_type='template'` renders as an outbound bubble labelled
  "Template · <name>".

### 9.1 Responses on the WhatsApp page

- A **Chat / Template responses** toggle (`SlideTabs`, like Home's Summary/Table) above the
  conversation list. Remembered per browser (`localStorage` `dd_wa_view`).
  - **Chat** — conversations with inbound messages through the **chat app**
    (`source_app IS NULL`), i.e. today's list.
  - **Template responses** — conversations with inbound messages through the **template
    app** (`source_app = 'template'`): the people who answered a campaign.
  - Both views keep paging, the real totals, search scope and RM scoping. The header count
    and "Create leads (N)" follow the view.
- A number that has inbound messages through **both** apps appears in **both** views and
  carries a red **+1** tag on its row (`--coral`, same chip shape as the tag chips), meaning
  "this person also talks to us on the other number". The thread itself is one
  conversation either way (one phone = one thread), so opening it shows everything.
- In **Template responses**, each row also shows the campaign that reached them last and,
  for a button tap, the button text.
- Sending a reply from a thread uses the app the customer **last wrote to** (§13.5), and the
  composer says which number it's sending from.
## 10. Rules and limits

- **Admins only**: every campaign/template endpoint `require_admin`. The cron calls the
  service directly, not over HTTP.
- **Send window**: IST wall-clock, default 10:00–19:00.
- **Pacing**: default 30/min per campaign, plus a global cap in the loop across campaigns.
- **Daily messaging limit (the "messaging tier")**: Meta limits how many **unique people**
  a business can message by template in a **moving 24h** — 250 → 2,000 → 10K → 100K →
  unlimited (Meta's current tiers; rev 5 corrected 1,000 to 2,000), rising automatically
  with volume while the quality rating (Green/Yellow/Red, driven by blocks and reports)
  holds. Replies inside a customer's 24h window don't count. Limits are set at the
  business-portfolio level, so the chat and template numbers may share one.
  `WA_DAILY_SEND_LIMIT` (config, default 250 — set it from WhatsApp Manager → Messaging
  limits): the preview/dry run warns above it, and the loop pauses while the last 24h
  (moving, not the calendar day) already holds that many people. (Billing, since July 2025: per delivered
  template message.)
- **Opt-out**: tagged `opted_out` by Meta's own signal (the user's "stop offers" control →
  a `preference-event` callback, and later sends failing with 131050) **and**, as our own
  policy, an inbound `STOP` (case-insensitive, trimmed) on either app — neither Gupshup nor
  WhatsApp acts on a typed STOP. Opted-out numbers are skipped by every manual and auto
  campaign.
- **Cooldown**: a number reached by a **different** campaign within N days is skipped
  (manual: warned and skipped, default 7 days; auto: its `cooldown_days`). A list repeat
  is not blocked by its own source campaign — repeating is the point.

## 11. API

All under `/v1/wa-campaigns`, `require_admin`. POST for every state change (CORS has no PUT).

| Method + path | Does |
|---|---|
| `GET /templates` · `POST /templates` · `PATCH /templates/{id}` | list / add / edit (locked fields refused once used) |
| `POST /preview` | upload or JSON (paste / contacts / `repeat_of` + mode) + template → validated rows + counts. **Writes nothing.** |
| `POST /` | create a manual draft from a validated payload |
| `GET /` | campaigns (manual + auto runs) with funnel counts |
| `GET /{id}` · `GET /{id}/recipients?status=` | one campaign + counts + buttons · its recipient rows with derived replies |
| `POST /{id}/launch` · `/pause` · `/resume` · `/cancel` | state changes |
| `POST /{id}/recipients/{rid}/retry` | re-queue a `failed` or stuck `submitted` row |
| `GET /{id}/export` | CSV, fetched as a blob |
| `GET /auto` · `POST /auto` · `PATCH /auto/{id}` | auto definitions: list / create (inactive) / edit |
| `POST /auto/{id}/dry-run` | who the next run would message + rendered samples. **Writes nothing.** |
| `POST /auto/{id}/activate` · `/deactivate` | on / off |
| `POST /auto/{id}/run-now` | create a run for today's slot immediately (same UNIQUE guard) |

## 12. Error handling

- Gupshup rejection on one recipient → that row `failed` with the text; the batch continues.
- Gupshup unreachable → the claimed row stays `submitted` ("Unknown — check"); the loop
  backs off and keeps the campaign `sending`.
- Template app not configured → launch / activate refuse with a 503 naming the missing vars.
- A template deactivated while an auto campaign uses it → the next run is skipped and the
  auto campaign shows "template inactive".
- Cron run fails mid-way → the transaction rolls back (no half-built run, `next_slot` not
  advanced); the task exits non-zero so Render shows the failure.

## 13. Open questions

1. **Messaging tier** — the template number's current daily limit (see §10; check in the
   Gupshup dashboard or WhatsApp Manager → Phone numbers → Messaging limit). Sets
   `WA_DAILY_SEND_LIMIT`.
2. **Button-reply payload shape** — confirm on the first real tap (§8.2).
3. **Lead sweep ↔ WhatsApp owner** — should `lead_assign` prefer an existing WhatsApp thread
   owner for the same phone? Outside this spec.
4. ~~Auto audience~~ — resolved in rev 3: auto runs repeat a list (§7.2).
5. **Replying from the right number** — a customer who answers the template number must be
   answered from it (the 24h window is per number). `/gupshup/send` needs to pick the app
   from the thread's latest inbound `source_app`. Proposed as part of build step 3.

## 14. Testing

Repo rule: tests never touch a database; assert the rules the SQL encodes.

- **Templates**: `variable_count` derived from `body`; locked fields refused once used.
- **Parsing/validation**: CSV + xlsx fixtures → phone10, slot count mismatch, duplicates,
  `+91` handling, defaults for blanks.
- **Claim is idempotent**: the claim SQL has `AND status='queued'`.
- **Receipts are forward-only**: `read` then `delivered` leaves `read`.
- **Attribution**: most recent prior campaign wins; button replies match by id.
- **Ownership**: WhatsApp owner → lead owner → least-loaded today; lead creation keeps it.
- **Opt-out / cooldown**: `STOP` tags `opted_out`; both exclusions apply to manual and auto.
- **Auto runs**: the UNIQUE (`auto_campaign_id`, `run_slot`) makes a second firing a no-op;
  `next_slot` advances in the same transaction; missed slots produce one run, not many;
  an inactive definition or template produces none; a still-sending previous run skips the
  slot; `non_responders` drops exactly the previous run's repliers; the always-removed
  set (§7.2) applies in both modes; an empty list or `max_runs` deactivates.
- **Repeat a list (manual)**: copies phone + variables, records `repeat_of`, re-validates.
- **Gupshup client** against `httpx.MockTransport` (pattern: `test_reassign_and_brochure.py`).
- **Frontend**: `npx tsc -b && npx vite build`, `check-theme.mjs`.
- **Before going live**: a manual campaign and one auto run to 1–2 internal numbers; confirm
  delivered / read / reply / button all land.

## 15. Build order

Each step ships and is verifiable on its own:

1. **Tables + templates** — all five tables, models; the Templates tab with add/edit/lock.
2. **Manual draft** — parsing, validation, the four sources (incl. repeat a list), preview,
   Save draft.
3. **Send loop** — template-app config + Gupshup call, claim, ownership, outbound
   `wa_messages` row, template bubble in chat, launch/pause/cancel; reply from the right app
   (§13.5).
4. **Tracking** — receipts → recipients, reply derivation, button rendering + attribution,
   detail page with boxes, table, export.
5. **Limits** — daily cap, `STOP` opt-out, cooldown.
6. **Auto campaigns** — definitions UI (seed, repeat mode, schedule), dry run,
   `run_auto_campaigns()`, the `wa_auto` cron task, runs listed per definition.
