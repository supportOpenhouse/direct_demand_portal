# API Contract — Direct Demand Portal

Single source of truth for the JSON wire format between `apps/web` and `apps/api`.
Both sides MUST conform exactly: snake_case keys, ISO-8601 UTC timestamps, all routes under `/v1`,
Bearer JWT auth on everything except `/v1/auth/*`.

Error envelope (all non-2xx): `{ "detail": string, "fields"?: { [field_name]: string } }`
(422 validation errors use `fields` keyed by the offending request field.)

## Enums

```
role          admin | cm | rm
source        meta | gads | 99acres | magicbricks | youtube | whatsapp | api | webhook | sheets
stage         new | contacted | visit_scheduled | visit_feedback | negotiation | won | lost | future_prospect | timepass
plan_to_buy   within_30_days | 1_3_months | 3_6_months | just_exploring
purpose       self_use | investment
office_willing yes | no | maybe
reminder_type follow_up | visit_schedule | visit_feedback | negotiation
supply_stage  msi | token_paid | negotiating
tat_state     ok | warn | breach   (or null once confirmed / not applicable)
matched_on    subset of [city, society, budget, config]
```

## Shared shapes

```ts
User        { id: string, name: string, email: string, phone: string|null,
              role: Role, team_id: string|null, team_name: string|null, active: boolean }
AssignedTo  { id: string, name: string }
TatInfo     { state: TatState|null, deadline: string|null, minutes_left: number|null }

LeadRow {
  id, name, phone, source, stage,
  is_hot: boolean, confirmed: boolean,
  city: string|null,
  society: string|null,          // from source data
  configuration: string|null,    // effective: confirmed over source
  budget_label: string|null,     // display: "₹70L – ₹90L" (band) or "₹85L" (confirmed value)
  plan_to_buy: PlanToBuy|null,
  assigned_to: AssignedTo|null,
  tat: TatInfo,
  qualified_at: string|null, created_at: string
}

SourceData    { budget_band: string|null, budget_min_lacs: number|null, budget_max_lacs: number|null,
                city: string|null, society: string|null, configuration: string|null, plan_to_buy: PlanToBuy|null }
ConfirmedData { purpose: Purpose|null, budget_value_lacs: number|null, configuration: string|null,
                office_willing: OfficeWilling|null, office_preferred_date: string|null,
                remark: string|null, confirmed_at: string|null }

Activity    { id, event: string, remark: string|null, actor_name: string|null, created_at }
Recording   { id, visit_id: string|null, file_ref: string, duration_sec: number,
              recorded_by_name: string|null, recorded_at: string }
VisitStop   { seq: number, inventory_id: string, name: string, society: string|null }
Visit       { id, trip_date: string, rm: AssignedTo|null, total_km: number, total_min: number,
              route_source: 'est'|'google', status: string, stops: VisitStop[] }

LeadDetail = LeadRow & {
  source_data: SourceData,
  confirmed_data: ConfirmedData|null,
  shortlist_societies: string[],     // Q4
  preferred_localities: string[],    // Q5
  activity: Activity[],              // newest first
  recordings: Recording[],
  visits: Visit[]
}

Unit {  // inventory and supply share this shape
  id, name, society: string|null, city: string|null, configuration: string|null,
  price_lacs: number|null, budget_min_lacs: number|null, budget_max_lacs: number|null,
  area_sqft: number|null,
  status: string|null,            // inventory only (e.g. available / resale)
  supply_stage: SupplyStage|null, // supply only
  eta: string|null,               // supply only
  interest_count: number,         // supply only (0 for inventory)
  lat: number|null, lng: number|null,
  image_url: string|null,
  ext_source: 'acquired_property'|'supply_tracker'
}

Match   { unit: Unit, score: number, match_pct: number, matched_on: MatchedOn[] }
Metrics { new: number, qualified: number, immediate: number,
          followups_due_today: number, pipeline: number, converted: number }
Reminder { id, lead_id: string, lead_name: string, type: ReminderType, note: string|null,
           due_at: string, done: boolean, auto_generated: boolean }
BucketMember { lead: LeadRow, score: number, match_pct: number, matched_on: MatchedOn[] }
Bucket  { id, unit: Unit, unit_kind: 'inventory'|'supply', member_count: number, members: BucketMember[] }

SocietyCard { society: string, city: string, buyers: number, hot_buyers: number,
              live_units: number, demand_gap: number,
              insights: { id, note, created_by_name: string|null, created_at }[] }
```

## Endpoints

### Auth
| Method/path | Req | Res |
|---|---|---|
| `POST /v1/auth/google` | `{credential}` (Google ID token) | `{token, user: User}` — 403 `{detail:"Account not provisioned"}` if email not in users table |
| `POST /v1/auth/dev-login` | `{email}` — only when `DEV_LOGIN_ENABLED=true`, else 404 | `{token, user}` |
| `GET /v1/me` | — | `User` |

### Leads
| `GET /v1/leads?segment=new\|qualified\|pipeline\|converted` | → `{items: LeadRow[], count: number}` (role-scoped) |
| `GET /v1/leads/{id}` | → `LeadDetail` (404 outside scope) |
| `POST /v1/leads/ingest` | `{name, phone, source, city?, society?, configuration?, budget_band?, budget_min_lacs?, budget_max_lacs?, plan_to_buy?}` → `LeadRow` 201. Round-robin assigns an active RM, sets TAT, logs activity, WhatsApp-stub alert. |
| `PATCH /v1/leads/{id}/source-data` | partial `SourceData` → `LeadDetail`. **403 unless admin.** |
| `POST /v1/leads/{id}/confirm` | `{purpose, budget_value_lacs, configuration, shortlist_societies: string[], preferred_localities: string[], office_willing, office_preferred_date?, remark?}` → `LeadDetail`. Missing Q1/Q2/Q3/Q6 → 422 with `fields`. Sets confirmed/qualified_at, stage new→contacted, clears TAT. |
| `POST /v1/leads/{id}/stage` | `{to_stage, remark}` (remark required → 422) → `LeadDetail` |
| `POST /v1/leads/{id}/hot` | `{is_hot: boolean}` → `LeadRow` |
| `GET /v1/leads/{id}/matches/inventory` · `/matches/supply` | → `Match[]` (top 5, ranked desc) |

### Reminders / visits / recordings
| `GET /v1/reminders?type=` | → `Reminder[]` (role-scoped via lead) |
| `POST /v1/reminders` | `{lead_id, type, note?, due_at}` → `Reminder` |
| `PATCH /v1/reminders/{id}` | `{done?}` → `Reminder` |
| `POST /v1/leads/{id}/visits` | `{trip_date, stops: [{inventory_id, seq}], total_km, total_min, route_source}` → `{visit: Visit, self_schedule_token: string}`. Sets stage visit_scheduled + auto visit_feedback reminder +2h. |
| `POST /v1/visits/{id}/recording` | `{file_ref, duration_sec}` → `Recording` |

### Inventory / supply
| `GET /v1/inventory` | → `Unit[]` |
| `GET /v1/supply` | → `Unit[]` |
| `POST /v1/supply/{id}/interest` | `{note?, lead_id?}` → `{interest_count: number}` |

### Gold Mine (admin/CM only — 403 for RM)
| `GET /v1/buckets` | → `Bucket[]` |
| `POST /v1/buckets/rematch` | → `{buckets: number}` |
| `POST /v1/buckets/{id}/broadcast` | `{mode: 'whatsapp'\|'call_list'}` → `{sent: number}` (WhatsApp stub logs) |

### Societies / metrics / admin
| `GET /v1/societies/insights` | → `{stats: {societies_tracked, total_demand, live_units, high_demand_gaps}, societies: SocietyCard[]}` |
| `POST /v1/societies/insights` | `{society, city, note}` → insight row |
| `GET /v1/societies` · `GET /v1/localities` | → `{name, city}[]` (reference lists for Q4/Q5) |
| `GET /v1/metrics/dashboard` | → `Metrics` (role-scoped) |
| `GET /v1/users` (admin) | → `User[]` |
| `POST /v1/users` (admin) | `{name, email, phone?, role, team_id?}` → `User` |
| `GET /v1/settings` (admin) | → `{integrations: [{key, label, enabled}], api_key_masked: string, webhook_url: string, assignment_method: string}` |
| `PATCH /v1/settings/integrations` (admin) | `{key, enabled}` → settings |
| `PATCH /v1/settings/assignment` (admin) | `{method}` → settings |
