# Direct Demand Dashboard — Interface Specification

A complete, framework-agnostic description of the UI so it can be rebuilt (in React) **pixel-identical** without reading the raw HTML. Every value below is the real value used in the prototype.

**Fidelity rule:** keep these tokens, class names, colours, fonts, sizes and layouts exactly. Don't substitute a component library or restyle.

---

## 1. Foundations

### Fonts (Google Fonts)
| Use | Family | Weights |
|---|---|---|
| Headings, numbers, logos | **Bricolage Grotesque** | 500–800 |
| Body / UI (default) | **Hanken Grotesk** | 400/500/600/700 |
| Phone numbers, mono chips, codes | **Spline Sans Mono** | 400/500/600 |

Base: `body` = Hanken Grotesk, **14px**, color `--ink`, background `--bg`, antialiased.

### Colour tokens (CSS variables)
**Neutrals (cool):**
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#f5f7fa` | app canvas |
| `--panel` | `#ffffff` | cards |
| `--panel-2` | `#f2f5f9` | inputs, subtle fills |
| `--ink` | `#0f172a` | primary text |
| `--ink-2` | `#46536b` | secondary text |
| `--muted` | `#8a94a6` | labels, meta |
| `--line` | `#e6eaf1` | borders |
| `--line-2` | `#eef1f6` | inner dividers |
| `--ink-sidebar` | `#0e1420` | sidebar base |
| `--ink-sidebar-2` | `#1a2434` | sidebar hover/active |

**Semantic accents (each has a `-soft` tint for chip backgrounds):**
| Token | Hex | Soft | Meaning |
|---|---|---|---|
| `--emerald` | `#059669` | `#d6f3e5` | won / success / confirm |
| `--blue` | `#2563eb` | `#dde8fe` | new |
| `--cyan` | `#0e8fa8` | `#cdeef4` | contacted / qualified |
| `--amber` | `#d68309` | `#fdeccb` | visit scheduled |
| `--violet` | `#7c3aed` | `#ebe5fd` | visit feedback |
| `--indigo` | `#4f46e5` | `#e2e2fc` | negotiation / pipeline |
| `--gold` | `#b8860b` | `#fbf0cc` | gold mine / supply hold |
| `--coral` | `#e11d48` | `#ffe1e6` | rejected + RNR / TAT breach |
| `--slate` | `#64748b` | `#eceff4` | follow up |

**Geometry:**
- `--radius: 14px` (cards). Chips ~6px, pills ~20px, buttons 9px.
- `--shadow: 0 1px 2px rgba(15,23,42,.04), 0 10px 30px -14px rgba(15,23,42,.16)`
- `--shadow-lg: 0 28px 64px -22px rgba(15,23,42,.40)` (modals, toasts)

---

## 2. App shell / layout

```
.app  = CSS grid, 248px sidebar | 1fr main, height 100vh, overflow hidden
└ .sidebar (dark)         └ .main (column)
                            ├ .topbar (60px, sticky, blurred white)
                            └ .view (scrollable, padding 26px)
```

### Sidebar (248px, dark)
- Background: `linear-gradient(180deg,#111a2b,#0e1420)`, right border `#080b12`, padding `18px 14px`.
- **Brand:** Openhouse logo SVG (38×38, orange flag + white house) + name "Openhouse" (Bricolage 17px white) / sub "DIRECT DEMAND" (10.5px, letter-spacing .14em, `#7c879c`).
- **Nav groups** with labels `WORKSPACE`, `DISCOVERY`, `ADMIN` (10px, uppercase, `#5a6577`).
- **Nav item:** flex, gap 11px, padding `9px 10px`, radius 9px, text `#a4adbe` 13.5px; **hover/active** → bg `--ink-sidebar-2`, text white; active has a **3px emerald (#10b981) bar** on the left edge.
- Item icons: 17×17 line SVGs (stroke 1.8).
- **Badges** (right-aligned): default red (`--coral`); `.gold` for Gold Mine; `.soft` (`#2a3445` bg / `#aeb7c5` text) for the lead-count tabs — Spline Mono, 10.5px.
- **User chip** (bottom): rounded `--ink-sidebar-2` block — avatar (initials), name (white), role/team (muted), and a role chip (`#9bbafb` on translucent blue). Clicking switches persona (prototype).

Nav order: **Dashboard · New Leads · Qualified Leads · Pipeline Leads · Converted Leads** (Workspace) — **Live Inventory · Supply Pipeline · Society Insights · Gold Mine** (Discovery) — **Settings & Access** (Admin).

### Topbar (60px)
- `rgba(255,255,255,.72)` + `backdrop-filter: blur(10px)`, bottom border `--line`, padding `0 26px`.
- Left: page title `<h1>` (Bricolage 20px) — Dashboard shows **"Hello, {user}"**; lead detail shows **"Lead Details"**.
- Right group: **search** (white pill, `--line` border, 240px), **orange "Reminders" button** with count badge, **green "Add New Lead" button**.

### View
- `flex:1; overflow-y:auto; padding:26px`. Custom scrollbar (`#d3dae5` thumb).

---

## 3. Colour-coding semantics (must match)

### Stage chips `.stage.<key>` — pill, dot + label, soft bg / accent text
| Stage | Colour |
|---|---|
| new | blue · call_not_received | cyan · follow_up | slate · qualified | indigo |
| visit_scheduled | amber · won | emerald · rejected + rnr | coral |

### Source badges `.src.<key>` — small square-dot chip, brand colours
| meta | blue (#1877f2) | gads | green (#34a853) | 99acres | orange (#ed5a0a) |
| magicbricks | magenta (#e63a73) | youtube | red (#ff0000) | whatsapp | green (#25d366) |

### TAT chip `.tat` (Spline Mono)
- `ok` = emerald soft/green · `warn` = amber soft · `breach` = coral soft, **pulsing** animation.

### Plan-to-Buy chip `.plan-chip`
- "Within 30 days" → **hot/emerald** · "1–3 months" → **warm/amber** · "3–6 months" → **cool/blue** · "Just exploring" → **cold/slate**.

---

## 4. Component catalog

### Buttons `.btn`
Pill, radius 9px, padding `9px 15px`, weight 600, 13px. Variants:
| Class | Look |
|---|---|
| `.primary` | ink (`#0f172a`) bg, white; hover near-black |
| `.green` | emerald bg, white (confirm/save) |
| `.wa` | `#25b15a` bg, white (WhatsApp) |
| `.ghost` | white bg, `--line` border, `--ink-2` text |
| `.gold` | gold bg, white |
| `.orange` | `#f97316` bg, white (Reminders) |
| `.sm` | smaller padding `6px 11px`, 12px |
- `.btn-badge` = translucent-white count pill inside a button.
- **`.wa-ico`** = 36×36 rounded-square green (`#25b15a`) icon button with the WhatsApp logo SVG.

### Cards `.card`
White, `--line` border, `--radius`, `--shadow`. `.panel-pad` adds 18px padding. `.panel-title` = bold 13.5px row with a 16px muted icon. `.section-head` = title + right action, space-between.

### KPI / stat cards `.stat` (used in `.kpi-row`, 3-col grid)
- Padding 18px; a **left accent bar** (`::after`, 3px, colour via `--accent`).
- `.k` = label (12px muted), `.v` = big number (Bricolage 30px), `.ico` = 30×30 rounded soft-tint square top-right with a line icon.
- `.clickable` → cursor + hover lift; cards link to their tab.

### Tables
- `th`: 11px uppercase muted, bottom `--line`. `td`: 13px, bottom `--line-2`, vertical-center.
- `tr.lead-row`: clickable, hover `--panel-2`.
- `.who` cell = avatar (32×32 gradient square, initials) + name (600) + phone (Spline Mono muted).

### Multi-select dropdown `.ms` (Q4/Q5)
- `.ms-toggle` = field-styled bar showing the selected summary + chevron; open state = emerald ring.
- `.ms-panel` = absolute white panel, `--shadow`, max-height 230 scroll; rows `.ms-opt` = checkbox (emerald accent) + label, hover `--panel-2`. Closes on outside click.

### Expandable option row `.opt` (matched inventory/supply)
- Wrapper `.opt` (bordered, radius 11). `.opt-row` = thumbnail (50×46 image) + info (name + green `match-mini` % chip; meta line `BHK · area · ₹ask`) + chevron + `.wa-ico`.
- Click row → toggles `.open` (chevron rotates 180°); `.opt-detail` reveals a key/value grid (`.opt-dl`) + (inventory only) a "↗ Share brochure" green button.

### Form fields `.field`
- Label (12px 600 `--ink-2`, required `*` in coral). Inputs/selects/textarea: full-width, `--line` border, radius 9, `--panel-2` bg; **focus** = emerald border + 3px emerald-soft ring. `.invalid` = coral border + soft bg. `.two` = 2-col grid. `.mand-flag` = coral warning, shown on validation fail.

### Office-visit pitch `.office-pitch` (Q6 No/Maybe)
- Gold-tinted box (`#fdf7e6` gradient, `#ead9a0` border): heading "💬 Pitch the office visit", an English bullet list, a dashed-top "HINGLISH" subheading, then an italic Hinglish bullet list.

### Modals
- `.overlay` = `rgba(10,15,25,.46)` + blur, centered. `.modal` = white, radius 18, `--shadow-lg`, slide-up animation. `.mh` header (title + ✕), `.mb` body (22px), `.mf` footer (right-aligned buttons, `--panel-2`). `.modal.wide` = up to 940px (visit planner).

### Toasts `#toasts` (bottom-right)
- Dark `--ink` pill, white text, `--shadow-lg`, coloured 26px icon square; kinds `wa/green/gold/blue`; slide-in, auto-dismiss ~3.4s.

### Misc
- **Switch** `.switch` (42×24 toggle, emerald when on). **`.note`** = dashed muted info box. **`.empty`** = centered muted empty state. **`.summary-box`** violet-tinted (AI summary — currently unused on lead page). **`.interest-bar`** = gold progress bar (society demand). **`.rec`** = visit-recording row with play button + faux waveform.

---

## 5. Screen layouts

**Dashboard** — `.kpi-row` (3 columns × 2 rows): New · Qualified · Immediate Buyers / Follow-ups due Today · Pipeline · Converted. (No other cards.)

**New Leads** — sub-text line + full-width card "New Leads: Urgent action required" with a cyan "Qualified Leads →" button; table columns: **Lead (name + source in brackets) · City · Society (from source) · Config (chip) · Budget · Plan to Buy (chip) · Assigned To · WhatsApp icon**.

**Qualified / Pipeline / Converted** — sub-text + one card with the standard lead table (Lead · Source · Stage(+outcome/follow chips) · TAT · Society · Assigned · "📅 Visits" action).

**Lead Details** — top: back link, avatar + name (+🔥 if hot) + phone/source/assignee. Two-column `.detail-grid` (1.4fr / 1fr):
- **Left:** "Lead data captured from Meta" (Budget, City, Society, Configuration, **Plan to Buy**; Admin-editable, locked badge for others) → "Lead data confirmed on call" (**Q1 Purpose · Q2 Budget ₹→lacs · Q3 Config · Q4 societies multi · Q5 localities multi · Q6 office Yes/No/Maybe + conditional date + pitch**; "Confirm & qualify lead") → **Activity** (timeline).
- **Right:** "Best matches from inventory" (5 expandable rows, ACQUIRED PROPERTY tag) → "From supply pipeline" (5 expandable rows, SUPPLY CLOSURE TRACKER tag) → "Visit recordings".

**Reminders** — tab filter pills (All / Follow-up / Visit schedule / Visit feedback / Negotiation) + list of typed reminder rows.

**Live Inventory** — 3-col grid of property cards (image, status/match tags, name, location, price, BHK/area chips, Share/Details).

**Supply Pipeline** — 3-col grid of supply cards with stage tag, ETA, buyer-interest bar, "I have a buyer" like + "Notify on landing".

**Society Insights** — section head + "+ Add society insight" gold button; 4 stat cards (Societies tracked / Total demand / Live units / High-demand gaps); 3-col grid of society cards (Buyers / Live units / Demand gap, demand bar, 🔥 immediate-buyer line, "💡 Buyer insights" list + per-card "+ Add").

**Gold Mine** — banner "New inventory lands → auto-bucket" + "+ Add this unit" gold button; stacked bucket cards (image header with count, matched-lead rows with reason + score, bulk WhatsApp / push-to-call); full table "All leads & their requirements" with a "Bucketed in" column.

**Settings & Access** — two cards: no-code integrations (toggle switches, API key & webhook code blocks) and Roles & access (Admin / CM / RM hierarchy + assignment-method select).

**Visit Planner (wide modal)** — trip date + RM; left inventory picker, right itinerary (Visit 1/2/3 with per-leg km/time + totals + "🧭 Optimize route"); full-width Google Map below.

---

## 6. Interaction states to preserve
- Nav/active highlight + left emerald bar. KPI card hover-lift. Row hover tint. Dropdown open ring + outside-click close. Option-row expand (chevron rotate). Field focus ring; invalid state + mand-flag. Q6 conditional show/hide (date on Yes/Maybe, pitch on No/Maybe). TAT breach pulse. Toast slide-in/out. Modal slide-up.

## 7. Icons
- **Line icons** (Lucide/Feather style, 24-viewBox, stroke `currentColor`) for nav + panel titles — reuse the exact SVG paths.
- **Brand SVGs:** Openhouse logo (orange/white), Meta "f", WhatsApp logo. Keep as inline SVG.

---

*Pair this with `HANDOVER.md` (architecture/schema/API) and `Openhouse-Direct-CRM-PRD.md` (product rules). The React app under `frontend/src/` is the exact reference if any value here is ambiguous.*
