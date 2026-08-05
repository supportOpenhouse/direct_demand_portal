# Live Calls — RM-facing view of a running dialer campaign

**Date:** 2026-08-05
**Status:** Approved design, ready for implementation planning

## Problem

When a dialer campaign runs, `_dial_next` rings the RM's handset first and bridges
the lead second (`backend/app/services/dialer.py:434`). The RM answers a call with
no idea who is on the other end, so they cannot prepare, cannot react, and cannot
record what happened.

Two things are missing:

1. The RM has no view of the campaign at all. Every `/v1/dialer/*` endpoint is
   `require_admin` (`backend/app/routers/dialer.py:87-272`).
2. The yes/no disposition flow exists (`CallConnected` →
   `POST /leads/{id}/call-result`) but is wired only into New Leads and Follow-up.
   Campaign calls have no way to be marked.

## Solution

A new RM-facing page, **Live Calls**, showing three sections — Completed, Now
Calling, Upcoming — fed by a Server-Sent Events stream with a REST snapshot and a
polling fallback.

## Decisions

These were settled during brainstorming and are not open questions:

| Decision | Choice |
|---|---|
| Page scope | All three sections: Completed + Now Calling + Upcoming |
| Disposition prompt | No popup. Completed rows carry a `⚠ needs result` badge; RM clicks when ready |
| "Yes" behaviour | Log the connected call, then navigate **same tab** to `/leads/{id}`; that page gets a back link to Live Calls |
| 2h spam blocker | Campaign-originated dispositions bypass it. A `dial_queue` row proves the system placed the call, so the anti-spam rationale does not apply. Manual worklist calls keep the blocker unchanged |
| Transport | SSE over Redis pub/sub, with REST snapshot + polling fallback |

## Constraints discovered in the codebase

These drive the design and must not be designed away.

**Auth cannot use native `EventSource`.** The frontend sends
`Authorization: Bearer <jwt>` from localStorage (`frontend/src/lib/api.ts:105`) and
is cross-origin to the API (Vercel → Render, via `VITE_API_URL`). Native
`EventSource` cannot set request headers. The common workaround — `?token=` in the
URL — leaks the JWT into access logs and referrer headers. The stream is therefore
consumed with `fetch()` + `ReadableStream`, which keeps the header.

**The publisher and subscriber can be different processes.** `render.yaml`
documents moving the scheduler to a separate Background Worker
(`RUN_SCHEDULER=false`) when scaling past one instance. `poll_open_calls` flips
`dial_queue` status there, while the Bonvoice webhook flips it in the web process.
An in-process event bus alone is insufficient; Redis pub/sub is required for the
documented scale path.

**Redis is optional.** `REDIS_URL` is `sync: false` in `render.yaml` and
`get_redis()` returns `None` when unset (`backend/app/cache.py:21`). The event bus
must degrade rather than fail.

**An RM is in at most one live campaign.** `_assert_no_rm_conflict`
(`backend/app/routers/dialer.py:36`) refuses to run a campaign sharing an RM with
another running campaign at overlapping hours. So "my campaign" resolves to at most
one row, and Live Calls is single-campaign by construction.

**`dial_queue.outcome` is taken.** It holds Bonvoice's telephony status, written by
the webhook (`backend/app/routers/bonvoice.py:596`) and the poller
(`backend/app/services/dialer.py:311`). RM disposition needs its own columns.

**Upcoming is only predictable under one strategy.** `dial_queue.rm_email` is
pre-stamped by `assign_owners` only under the `assigned` strategy. Under
`round_robin` and `least_load` it is `NULL` until `_dial_next` claims it
(`backend/app/services/dialer.py:459-465`). The UI must label the shared case
honestly rather than imply ownership.

## Architecture

```
 _dial_next()          bonvoice webhook          poll_open_calls()
 (dialer proc)          (web proc)                (dialer proc)
      │                      │                          │
      └──────────────┬───────┴──────────────────────────┘
                     ▼
              events.publish("rm:<email>", {...})
                     │
        ┌────────────┴───────────────────┐
        │ Redis PUBLISH                  │  REDIS_URL set
        │ in-process asyncio fan-out     │  REDIS_URL unset
        └────────────┬───────────────────┘
                     ▼
        GET /v1/dialer/my-calls/stream   (SSE, current_user)
                     │  fetch() + ReadableStream
                     ▼
              LiveCalls.tsx
```

The stream carries only invalidation nudges —
`{type: "call_started" | "call_ended", queue_item_id}` — and the page refetches the
REST snapshot. One authoritative query builds the payload; the stream never
duplicates it.

## Backend components

### `backend/app/events.py` (new)

Mirrors `cache.py`'s contract: lazy, optional, swallows errors.

```python
async def publish(channel: str, payload: dict) -> None
async def subscribe(channel: str) -> AsyncIterator[dict]   # yields until cancelled
```

With Redis: `PUBLISH` / `pubsub.listen()`. Without: a module-level
`dict[str, set[asyncio.Queue]]` fan-out. Identical interface, so no caller branches
on which is active. A publish failure is logged and dropped — a lost nudge costs at
most one refetch, and the polling fallback still catches the state change.

### Schema

Three additive columns in `_ADD_COLUMNS` (`backend/app/migrations.py`):

```python
("dial_queue", "call_result",    "TEXT"),         # 'connected' | 'missed'
("dial_queue", "call_result_at", "TIMESTAMPTZ"),
("dial_queue", "call_result_by", "TEXT"),
```

`outcome` is untouched.

### `GET /v1/dialer/my-calls`

Auth: `current_user` (not `require_admin`). Resolves my campaign as `status='running'`
AND my email in `rms` AND the calling window currently open.

Returns:

- `campaign` — id, name, strategy, or `null` when none is live
- `now_calling` — my `dialing` row joined to the lead: name, phone, society, config,
  budget, stage, prior call count
- `upcoming` — under `assigned`, my `pending` rows ordered by `position`; otherwise
  the shared `pending` pool with `shared: true`
- `completed` — rows where `dialed_at IS NOT NULL` and `rm_email` is me, newest
  first, each carrying `call_result` so the UI can badge the unmarked ones. "Today"
  means the current **IST** calendar day (`dialed_at AT TIME ZONE 'Asia/Kolkata'`),
  matching the IST calling windows the campaign already runs on — not UTC, which
  would roll the list over at 05:30 IST mid-shift

This endpoint serves both the initial snapshot and the polling fallback.

### `GET /v1/dialer/my-calls/stream`

SSE via `StreamingResponse`, subscribed to `rm:<my-email>`. Keepalive comment every
25s so Render does not idle the connection out. Cancels cleanly on client
disconnect.

### `POST /leads/{id}/call-result` (extended)

Gains an optional `queue_item_id`. When present:

1. Verify the queue row belongs to `current_user` — 403 otherwise. Ownership is
   re-checked server-side; the client never asserts it.
2. Skip the `NO_COOLDOWN_HOURS` check (`backend/app/routers/leads.py:372`).
3. Stamp `call_result`, `call_result_at`, `call_result_by`.

Every existing rule runs unchanged: miss reasons, `_within_calling_hours` clamping,
RNR escalation at 10 misses, Invalid Number → Rejected. When `queue_item_id` is
absent the endpoint behaves exactly as it does today.

### Publishers

Three sites, one `publish` call each:

- `_dial_next` after `place_bridge` succeeds (`backend/app/services/dialer.py:487`)
- the Bonvoice hangup upsert (`backend/app/routers/bonvoice.py:596`)
- `poll_open_calls` (`backend/app/services/dialer.py:311`)

## Frontend components

### `frontend/src/lib/useEventStream.ts` (new)

`fetch()` with the `Bearer` header, reads `response.body` as a `ReadableStream`,
parses SSE frames, invokes `onEvent`. Reconnects with backoff (1s, 2s, 4s, 8s,
capped at 15s); after 3 consecutive failed connection attempts it reports unhealthy
so the caller can fall back to polling. It keeps retrying at the capped interval in
the background, and reports healthy again the moment a connection succeeds.

### `frontend/src/lib/queries.ts`

`useMyCalls()` — react-query with `refetchInterval: false` while the stream is
healthy, `4000` when it is not. The stream's `onEvent` calls `invalidateQueries`, so
the live and fallback paths converge on one code path and a dropped connection
degrades to plain polling rather than to nothing.

### `frontend/src/components/CallConnected.tsx` (refactor)

Export `MissReasonModal`, currently module-private. Add an optional `queueItemId`
to it and to `useCallResult`. New Leads and Follow-up pass nothing and are
unaffected.

### `frontend/src/pages/LiveCalls.tsx` (new)

- **Now Calling** — lead card. Idle empty state when no call is live.
- **Upcoming** — labelled "next in shared pool — may go to another RM" whenever
  `shared: true`.
- **Today** — completed rows. `call_result IS NULL` renders an amber
  `⚠ needs result` badge. Clicking opens the yes/no. **Yes** logs the connected call
  and navigates same-tab to `/leads/{id}`. **No** opens the miss-reason modal.

### Route and navigation

`/live-calls` in `frontend/src/App.tsx`, plus a Sidebar entry under **Workspace** —
this is the RM-facing half of the dialer, not an admin tool. Visible to every
authenticated user; it only ever shows the caller's own rows, so no role gate is
needed.

The "Yes" navigation passes react-router state (`navigate(url, { state: { from:
"live-calls" } })`). `LeadDetail` renders a "← Live Calls" back link when that state
is present and nothing otherwise, so arriving from any other page is unchanged.

## Error handling

| Failure | Behaviour |
|---|---|
| `REDIS_URL` unset | In-process fan-out. Correct on a single instance, the only config where Redis is legitimately absent |
| Redis down mid-run | `publish` swallows; subscribe errors; hook falls back to 4s polling |
| Stream drops | Backoff reconnect; polling covers the gap; 25s keepalives prevent most idle drops |
| No running campaign | Idle empty state, not an error. Today's completed rows still render so pending dispositions stay reachable |
| `queue_item_id` not mine | 403, verified server-side |
| Retry cleared the row | Disposition targets the queue row by id; a stale id 404s rather than writing to the wrong attempt |

**Known gap:** `RUN_SCHEDULER=false` together with an unset `REDIS_URL` means the
dialer runs in a process the web instance cannot hear, so events never arrive and
only the polling fallback works. A startup warning is emitted for that exact
combination rather than letting it fail silently.

## Testing

The repo runs `pytest` with `asyncio_mode = "auto"` and **no live database**. Tests of
DB-heavy code follow `test_wa_assign.py`'s convention: assert the *rules the SQL
encodes* by inspecting the statement text, so a bad edit to a query is caught without
a Postgres. New tests follow the same convention.

- **`test_events.py`** — fully executable async tests of the in-process fan-out:
  publish/subscribe round trip; publish with no subscriber is a no-op; a subscriber
  that raises does not poison the channel for other subscribers; unsubscribe removes
  the queue.
- **`test_live_calls.py`** — SQL-text assertions on the `my-calls` queries: every
  query filters on `rm_email`; `completed` uses the `Asia/Kolkata` day boundary, not
  UTC; `upcoming` restricts to `rm_email` only under `assigned`. Plus executable
  tests for the pure helpers (campaign resolution, `shared` flag derivation).
- **Cooldown bypass** — executable test that the `blocked` clause is
  parameterised on `skip_cooldown` and that `call_result` passes `True` exactly when
  a verified `queue_item_id` is present. This is the only behaviour change to
  existing logic, so it is tested in both directions.
- **Regression** — `test_dialer.py` and the lead worklist tests stay green. New Leads
  and Follow-up pass no `queue_item_id` and must behave identically.

## Out of scope

- Manually-placed calls. Live Calls is campaign-scoped.
- Any change to how the scheduler paces or assigns calls.
- An inline confirm form. "Yes" navigates to `LeadDetail`, which already owns that
  form.
