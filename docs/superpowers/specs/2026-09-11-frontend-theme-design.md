# Direct Demand Portal — frontend theme rebuild

**Status:** design approved 11 Sep 2026. **Phases 1–5 implemented and verified 11 Sep.**
**Phase 6 (per-page accent) implemented 11 Sep** — `/inventory` and `/supply` carry the
supply orange via `data-accent="orange"` on `<html>`.
Follow-on work (Home rename + Summary/Table, lead popup) landed the same day.
**Scope:** `frontend/` only. No backend change, no API change.

---

## 1. Goal

Replace the frontend's single hardcoded light theme with a tokenized design system
carrying light + dark modes, brand accent `#2c66eb`, motion, a profile page, filters on
every list page, and `react-icons` in place of emoji/symbol literals.

The pattern being ported is `Direct_Inventory/frontend/src/styles.css` (1810 lines) and
its `ThemeContext.jsx` / `FilterPanel.jsx` / `MyProfile.jsx`. That repo already solved
this problem; this is a port, not an invention.

**What is NOT being taken from Direct Inventory:** its 4-colour stage palette. Direct
Demand's eight-hue stage ramp stays exactly as it is — same stages, same hues, same
meanings.

---

## 2. Starting state (measured 11 Sep 2026)

```
frontend/src/styles/app.css       1585 lines · 379 class selectors · 15 @keyframes · 71 transitions
  hardcoded colour outside :root  283 hex literals (123 unique) + 38 rgba()
frontend/src/**/*.tsx             47 hex literals across 17 files
frontend/src/components/icons.tsx 16 hand-rolled SVG icons
emoji / symbol literals           ~40 across Settings, NewLeads, Stub, VisitPlanner, useSort, …
pages                             24 desktop routes + a separate MobileApp tree
filters                           Filters.tsx, 170 lines, an inline row of <select>s
theme                             none — no ThemeContext, no data-theme, light only
profile page                      none
logout                            onClick on the whole UserChip row in Sidebar.tsx
```

Those 368 hardcoded colour values are the actual work of Phase 1. Dark mode is only as
complete as the last literal that was missed.

### 2.1 One thing that is already right

Stage chips are **already fully tokenized**:

```css
.stage.new      { background: var(--blue-soft);    color: var(--blue) }
.stage.contacted{ background: var(--cyan-soft);    color: var(--cyan) }
.stage.planned  { background: var(--slate-soft);   color: var(--slate) }
.stage.nego     { background: var(--indigo-soft);  color: var(--indigo) }
.stage.visit    { background: var(--amber-soft);   color: var(--amber) }
.stage.won      { background: var(--emerald-soft); color: var(--emerald) }
.stage.lost     { background: var(--coral-soft);   color: var(--coral) }
```

`lib/leads.ts` maps all nine stages onto those seven classes. Giving the stage ramp a
dark mode is therefore **16 token redefinitions and zero class changes**.

---

## 3. Approach

**Tokenize `app.css` in place.** Keep the file, keep all 379 class names, replace the
283 hex + 38 rgba with tokens, add a `[data-theme='dark']` block, and sweep the 47 TSX
literals. Every page inherits dark mode the moment its classes point at tokens — no page
rewrites.

Rejected alternatives:

| Approach | Why not |
|---|---|
| Fresh `tokens.css` + rewrite `app.css` against it | Re-derives 379 working selectors; every page becomes a regression risk. Buys tidiness, costs a week. |
| Layer tokens on top, tokenize page-by-page as pages get touched | Ships a half-dark app for weeks. A patchy dark mode is worse than none. |

---

## 4. Phase 1 — token layer and dark mode

### 4.1 Brand

The accent swaps with the theme, the way Direct Inventory swaps orange → hot pink.

```css
:root, [data-theme='light'] {
  --brand:        #2c66eb;
  --brand-strong: #1d4fd0;
  --brand-soft:   #e8f0fe;
  --brand-softer: #f4f8ff;
  --brand-ring:   rgba(44, 102, 235, .18);
  accent-color:   var(--brand);
}
[data-theme='dark'] {
  --brand:        #07b6d4;
  --brand-strong: #22d3ee;
  --brand-soft:   rgba(7, 182, 212, .18);
  --brand-softer: rgba(7, 182, 212, .10);
  --brand-ring:   rgba(7, 182, 212, .32);
}
```

### 4.2 Surfaces, text, lines

Light mode keeps today's cool near-white canvas (`--bg:#f5f7fa`) so the existing stage
chips still read correctly. Dark mode is a cool-neutral ladder, not pure black:

```
                 light            dark
--bg             #f5f7fa          #0f1115
--panel          #ffffff          #161a20
--panel-2        #f2f5f9          #1d222a
--ink            #0f172a          #f1f4f9
--ink-2          #46536b          #c2cad8
--muted          #8a94a6          #8892a3
--line           #e6eaf1          #262d38
--line-2         #eef1f6          #1f252e
```

The existing `--radius` / `--shadow` / `--shadow-lg` tokens stay; shadows get dark-mode
values (higher opacity, black rather than slate).

### 4.3 Sidebar

Light stone rail. The sidebar stops being the dark navy slab it is today:

```
                     light            dark
--sidebar-bg         #ffffff          #0b0d11
--sidebar-fg         #5a6478          #9aa4b4
--sidebar-fg-dim     #96a0b2          #6b7585
--sidebar-fg-strong  #0f172a          #ffffff
--sidebar-hover      #f2f5f9          rgba(255,255,255,.06)
--sidebar-active-bg  var(--brand-soft)
--sidebar-active-fg  var(--brand)
--sidebar-border     var(--line)      rgba(255,255,255,.07)
```

`#2c66eb` (light) / `#07b6d4` (dark) appears in the rail **only** as the active item's
tint pill and its 3px edge indicator. The active indicator today is a hardcoded
`#10b981` green — it becomes `var(--brand)`.

The brand lockup PNG is black-on-transparent ink. On the white light rail it needs no
filter (today's `invert(1) hue-rotate(180deg)` is for the navy rail and must be removed
for light mode); in dark mode the same filter pair applies. Guard this with a
`[data-theme='dark']` selector rather than an unconditional filter.

### 4.4 Stage ramp in dark mode

Keep all eight hues and every stage→hue mapping. Add dark variants of the sixteen
tokens, because the `-soft` values are *light backgrounds* (`--blue-soft:#dde8fe`,
`--emerald-soft:#d6f3e5`, …) and would glow on a dark canvas.

Two constraints on the dark values:

1. Each `-soft` becomes a low-alpha wash of its own hue; each solid becomes a lifted,
   less-saturated version that clears 4.5:1 against `--panel`.
2. **`--cyan` (Call Not Received) must be pulled away from the dark brand `#07b6d4`.**
   In dark mode the brand *is* cyan, so the stage and the accent would otherwise read as
   the same colour. Shift the dark `--cyan` toward teal-green (`~#2dd4bf`) — same stage,
   same slot in the ramp, distinguishable from the accent.

`--blue` (New) is `#2563eb`, essentially the light-mode brand. That collision only exists
in *light* mode, where a New chip sits next to a brand-blue button. **Default: leave it
alone.** Change the light `--blue` only if the two actually read as one colour on screen —
that is a judgement to make while looking at the running app, not here.

### 4.5 Motion tokens

Ported verbatim from Direct Inventory — named for the job, not the number:

```css
:root {
  --t-press:.1s;  --t:.14s;  --t-move:.18s;  --t-enter:.24s;  --t-sheet:.28s;
  --ease:      cubic-bezier(.4,0,.2,1);
  --ease-out:  cubic-bezier(.22,.61,.36,1);
  --ease-inout:cubic-bezier(.76,0,.24,1);
}
```

The 71 existing transitions in `app.css` get re-pointed at these, so a retune is one edit.

### 4.6 Typography

Fraunces (headings) + Inter (body) replace Hanken Grotesk, matching Direct Inventory:

```css
body      { font-family:'Inter', system-ui, -apple-system, sans-serif }
h1,h2,h3,h4 { font-family:'Fraunces', Georgia, serif; font-weight:600; letter-spacing:-.01em }
```

"Spline Sans Mono" stays for numeric badges and tabular figures.

### 4.7 ThemeContext

Port `ThemeContext.jsx` → `frontend/src/components/ThemeContext.tsx`:

- `data-theme` attribute on `<html>`, persisted to `localStorage` under `dd_theme`.
- Default **light**, ignoring the OS preference; an explicit toggle is remembered.
- Toggle runs through `document.startViewTransition` with a random-direction curtain
  wipe (`ltr/rtl/ttb/btt`), `flushSync` so the re-render lands before the "new" snapshot,
  and a plain `setTheme` fallback where the API is absent.
- Provider wraps the tree in `main.tsx`, outside `RouterProvider`.

### 4.8 Definition of done for Phase 1

- `npx tsc -b && npx vite build` clean.
- A grep guard fails the phase if a raw hex or `rgba(` appears in `app.css` outside the
  token blocks, or in any `.tsx`. This is the only mechanical check that dark mode is
  actually complete.
- Every desktop route plus the `MobileApp` tree renders correctly with the theme
  toggled both ways.

---

## 5. Phase 2 — shell, profile, logout

- Sidebar repainted onto the `--sidebar-*` tokens from §4.3.
- **Logout is separated from the user chip.** Today `UserChip` puts `onClick={logout}`
  on the entire row, so clicking your own name signs you out — which is exactly why a
  profile page has had nowhere to live. New behaviour: the chip navigates to `/profile`;
  a distinct power icon beside it logs out.
- New route `/profile`, `pages/Profile.tsx`: identity (name, email, avatar), role chip,
  theme toggle, sign out. Shape ported from `MyProfile.jsx` minus its scope-map and
  micro-market panels, which are Direct Inventory concerns.
- Topbar carries the theme toggle as well, so it is reachable from every page.
- The dev-only `DevViewAs` switcher stays where it is and stays compile-time gated.

---

## 6. Phase 3 — motion

Ported from Direct Inventory:

| What | Mechanism |
|---|---|
| Route transitions | `pageInRight` / `pageInLeft` / `pageFade` on the view container |
| Skeleton loads | `.inv-skel` shimmer, applied to every table and card list while a query is pending |
| Modal enter/exit | `modal-in` / `modal-out` + scrim fade; exit travels downward |
| Sheets / drawers | `sheet-in` |
| Toasts | `toastIn` |
| Spinners | `btn-spinner`, `busy-spinner` |
| Theme change | the View-Transitions curtain wipe from §4.7 |
| Login | an entrance fade + rise around the existing Google GSI button |

Login uses the short fade, **not** Direct Inventory's 1.7s welcome curtain, unless asked
for later — a 1.7s hold is a long time to look at on every sign-in.

Every animation gets a `@media (prefers-reduced-motion: reduce)` off-switch, matching the
source repo.

The 15 existing `@keyframes` in `app.css` stay; they get re-pointed at the motion tokens
for their durations and easings.

---

## 7. Phase 4 — react-icons

- Add `react-icons` as a dependency; import per-icon so the bundle tree-shakes.
- Replace the 16 hand-rolled SVGs in `icons.tsx` and the ~40 emoji/symbol literals
  (`🚧 📍 🎉 ⚠ ✓ ✕ ✎ 👁 🙈 ⬇ ▲ ▼ →`) across `Settings.tsx`, `NewLeads.tsx`, `Stub.tsx`,
  `VisitPlanner.tsx`, `useSort.tsx`, `ReportDetail.tsx`, `Logs.tsx` and the rest.
- `icons.tsx` **stays as the single import surface** — it re-exports named icons from
  `react-icons` under the existing `IconFoo` names, so pages change one import line
  rather than twenty call sites, and swapping icon sets later is one file.
- `→` inside CSS comments and prose is not an icon. Only replace glyphs that render.

---

## 8. Phase 5 — filters on every list page

Its own spec; sketched here only so the boundary is clear.

Shape: **inline removable chips + a Filters modal.**

```
┌────────────────────────────────────────────┐
│ New Leads                     ⚙ Filters    │
│ ┌────────────────────────────────────────┐ │
│ │ Noida ✕   Meta ✕   This week ✕   clear │ │
│ └────────────────────────────────────────┘ │
├────────────────────────────────────────────┤
│ NAME      PHONE     CITY    SOURCE    TAT  │
```

Active filters are always visible as chips; the modal carries the long tail
(multi-select society, budget ranges, date presets, saved presets). Ported from
`FilterPanel.jsx` + `PresetBar.jsx` + `SearchableMultiSelect.jsx`.

`Filters.tsx`'s existing `countedOptions` / `matchesOption` / `inDatePreset` /
`uniqueValues` logic **survives unchanged** — it is the faceting brain, including the
subtle bit where a selected value whose facet count drops to zero is pinned so the
`<select>` never silently snaps back to "All". Only the presentation is replaced.

18 list pages. Separate spec, separate plan.

---

## 9. Phase 6 — per-page accent (deferred)

**Deferred by request on 11 Sep — recorded here, not scheduled.**

On **Live Inventory** (`/inventory`) and **Supply Pipeline** (`/supply`) the accent
changes from blue to orange, and the change animates rather than snapping.

Those two pages are the supply side — the same domain Direct Inventory owns, whose brand
is `#fa541c`. Using that orange makes the accent shift mean something rather than being
decoration.

**Most of this already exists.** `app.css` (the `LIVE INVENTORY` section) already
declares a complete orange palette scoped to `.snap-page` — it was ported from the CRM
so the page "reads identically to the one the team already shares from". Phase 1 pointed
its members at the shared supply-orange tokens, so the block now reads:

```css
.snap-page{
  --acc:var(--supply-orange); --accDark:var(--supply-orange-2);
  --accBg:var(--supply-orange-soft); --accBg2:var(--supply-orange-soft-2);
  ...
}
```

Phase 6 is therefore not "build a per-page accent system". It is: rename that private
`--acc*` namespace onto the shared `--brand-*` one, and move the scope from a class to a
root attribute so Supply Pipeline gets it by adding the attribute rather than by
duplicating the block.

Mechanism: a `data-accent="orange"` attribute set on the root from the route, redefining
only the five `--brand-*` tokens. Nothing else in the system moves.

```css
[data-accent='orange'] {
  --brand:#fa541c; --brand-strong:#d9430f;
  --brand-soft:#fff1ec; --brand-softer:#fff7f4;
  --brand-ring:rgba(250,84,28,.18);
}
```

**The transition is the part with a trap in it.** Custom properties are not animatable
unless registered, so `transition: --brand .3s` does nothing on its own. Two things are
therefore true:

- Any element that *already* has a transition on the property it paints with
  (`transition: background var(--t)` and friends — 71 such declarations exist) animates
  for free when `--brand` changes underneath it. Most of the UI is in this group.
- Anything painted **without** a transition animates nowhere and will snap: SVG
  `fill`/`stroke`, `box-shadow`, and the `::before` active rails. Those need explicit
  transitions added, or `@property --brand { syntax:'<color>'; inherits:true }`
  registration so the variable itself interpolates.

Open for this phase, to settle when it is actually built: whether orange also swaps in
dark mode (`#fa541c` is legible on `#0f1115`, so probably it stays, brightened toward
`#ff7a45`), and whether the accent should follow a route change or only a full page load.

---

## 10. Delivery

One phase at a time. Built and verified against the running app, then verified locally by
the user before the next phase starts — the same working agreement as the Group A change
spec.

| Phase | Content | Gate |
|---|---|---|
| 1 | Token layer, dark mode, ThemeContext, fonts, motion tokens | build clean · hex grep guard clean · all routes both themes |
| 2 | Sidebar, topbar, `/profile`, logout split | build clean · sign-out and profile reachable, chip no longer logs out |
| 3 | Motion: routes, skeletons, modals, login | build clean · reduced-motion honoured |
| 4 | react-icons migration | build clean · no emoji renders in the UI |
| 5 | Filters (own spec) | — |
| 6 | Per-page accent (deferred) | — |

Each phase leaves the app shippable.

### Verification

There is no frontend test infrastructure in this repo and this spec does not add one —
a theme port is verified by looking at it. The mechanical gates are:

```
cd frontend && npx tsc -b && npx vite build
grep -nEi '#[0-9a-f]{3,8}\b|rgba\(' src/styles/app.css   # expect: token blocks only
grep -rnEi '#[0-9a-f]{6}\b' --include='*.tsx' src        # expect: nothing
```

The human gate is the dev server with the theme toggled on every route.
