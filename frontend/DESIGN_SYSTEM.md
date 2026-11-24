# Unique Type — Design System v4 "Editorial"

Premium · Authoritative · Conversion-aggressive.

**The palette is the logo.** Its two interlocking links — deep blue and saffron — are the
whole colour system: blue is the ground and the informational voice, saffron is the only
thing that ever asks you to act.

More trustworthy than a government portal, sharper than TenderDetail or TenderTiger,
more confident than typical Indian B2B SaaS. Built for an MSME owner who is about to
hand over their tender documents and wants to know this is serious.

Tokens live in `tailwind.config.js`. Primitives live in `src/index.css`.
**Do not hardcode a hex value in a component.** If a colour is missing, add a token.

---

## 0. Themes

Light and dark, plus **system** (the default, and what most people want — it follows
the OS, including when the OS flips at sunset). Choice is stored under `taa-theme` and
applied as `<html data-theme="light|dark">`.

An inline script in `index.html` resolves the theme **before first paint**. Without it,
dark-theme users get a white flash on every load. It must stay inline and stay in `<head>`.

### Semantic tokens — the only things that flip

Use these for anything that is "a page", "a card", "a hairline" or "body text". They are
CSS variables, so one declaration covers both themes.

| Token | Light | Dark | Use |
|---|---|---|---|
| `canvas` | `#F8FAFC` Off White | `#0A0F1A` | Page ground |
| `panel` | `#FFFFFF` Pure White | `#1A2332` Charcoal | Cards, raised surfaces |
| `sunk` | `#F1F5F9` Light Gray | `#0F172A` Deep Navy | Table heads, subtle fills |
| `edge` | `#E2E8F0` | `#243044` | Hairline — the default border |
| `edge-strong` | `#CBD5E1` | `#33425A` | Emphasised border, inputs |
| `fg` | `#0F172A` Deep Navy | `#F8FAFC` Off White | Primary text |
| `fg-muted` | `#475569` (7.6:1) | `#94A3B8` (6.2:1) | Secondary text |
| `fg-subtle` | `#64748B` Cool Gray (4.8:1) | `#7E90A9` (4.9:1) | Tertiary text, mono labels |
| `accent` | `#B84B00` | `#FF8A00` Warm Orange | Orange *text* |
| `accent2` | `#0052CC` Primary Blue | `#5B9BFF` | Blue *text*, links |

`bg-panel/60`, `border-edge/50` etc. all work — tokens are stored as RGB channels.

### `.on-dark` — navy in both themes

The hero bands, the footer, the sidebar rail and the run console stay navy whichever
theme is active. **The brand should not change colour because someone turned the lights
off.** Those elements carry `.on-dark`, which re-points the tokens locally — so the same
`text-fg-muted` that is slate on a white card is light steel inside them, and no
component needs to know which ground it landed on.

```html
<section class="on-dark bg-navy-900">…</section>
```

Raw `navy-*` / `steel-*` / `saffron-*` values remain correct for anything that must stay
that colour in both themes. Everything else uses the semantic set.

**Verify with the contrast probe, not by eye.** Walk every route in both themes and
assert zero pairs below 4.5:1 (3:1 for large text). Real bugs it has caught: index
numbers at `steel-400` on white (2.56:1), a navy secondary button on a navy card in dark,
a fixed `saffron-50` callout with near-white text on it, and legal copy left on a legacy
near-black alias (1.0:1 on a dark panel).

---

## 1. Colour — the brand palette

These are the brand's specified values. Every one is present; nothing was substituted.

| Name | Hex | Token | Use |
|---|---|---|---|
| Primary Blue | `#0052CC` | `azure-600` / `accent2` (light) | Headers, links, icons — 6.8:1 on white |
| Bright Blue | `#1E6BFF` | `azure-500` | Hover states |
| Vibrant Orange | `#FF6B00` | `saffron-500` | **Main CTAs** — Start Free Trial |
| Warm Orange | `#FF8A00` | `saffron-400` / `accent` (dark) | Secondary highlights, accent on dark |
| Deep Navy | `#0F172A` | `navy-900` / `fg` (light) | Headings and main text |
| Charcoal | `#1A2332` | `navy-800` / `panel` (dark) | Dark sections |
| Cool Gray | `#64748B` | `steel-500` / `fg-subtle` (light) | Secondary text — 4.8:1 |
| Light Gray | `#F1F5F9` | `steel-100` / `sunk` | Backgrounds |
| Off White | `#F8FAFC` | `steel-50` / `canvas` | Section backgrounds |
| Pure White | `#FFFFFF` | `panel` (light) | Cards |

### Three derived values, and why they exist

The palette above is complete for surfaces. Three text colours had to be derived
because a brand hex, used directly as text, failed WCAG AA:

| Derived | From | Why |
|---|---|---|
| `#B84B00` | Vibrant Orange | Orange **text** on light. `#FF6B00` is 2.9:1 on white — unreadable. This shade is 5.2:1 on white and clears 4.5:1 on Light Gray and Off White too |
| `#5B9BFF` | Bright Blue | Links on dark. `#1E6BFF` is only 3.5:1 on Charcoal; this tint is 5.7:1 |
| `#94A3B8` | Cool Gray | Secondary text on dark. `#64748B` is 3.3:1 on Charcoal; this tint is 6.2:1 |

The brand hexes remain the fills, borders, icons and graphics. The derived shades are
used only where the same hue must carry small text.

### The CTA carries Deep Navy text, not white

**White on Vibrant Orange measures 2.86:1** — it fails AA at every size, and on the one
button the whole page is built to drive. Deep Navy `#0F172A` on the same orange is
**6.25:1**, so the CTA keeps its exact specified fill and the label stays legible.
Hover goes to Warm Orange `#FF8A00` (7.6:1 with the same navy).

### Division of labour

- **Orange = act on this.** CTAs, live/running state, the rule above a heading.
- **Blue = navigate or note.** Links, headers, icons, the "submitted" state, info chips.
- **Navy / Charcoal = the ground.** Deep Navy is the page dark; Charcoal is a section
  or card raised off it.

Blue never takes an action; if it competed with orange the CTA would stop reading as the
one thing to click.

### Status — one token per meaning
Never pick a raw colour for state.

| Token | Hex | Means |
|---|---|---|
| `status-ok`   | `#3B6650` | Cleared, verified, won |
| `status-warn` | `#B45309` | Expiring, needs attention |
| `status-risk` | `#B42318` | Disqualifying, expired, lost |
| `status-info` | `#0052CC` | Informational, submitted — Primary Blue |
| `status-idle` | `#94A3B8` | Queued, not started |
| `status-live` | `#FF6B00` | Running right now — Vibrant Orange |

### Legacy aliases
`ink-*`, `bone-*`, `brass-*`, `cream-*`, `gray-*`, `blue-*` are remapped onto the new
palette so ~800 references in untouched product screens carry across. **Do not use them
in new code.**

---

## 2. Typography

| Role | Family | Notes |
|---|---|---|
| Display | **Inter Tight** 600–800 | Geometric, tight tracking. No serifs anywhere |
| Body | **Inter** 400–600 | `ss01`, `cv11`, `calt` on |
| Data | **JetBrains Mono** | Every ₹, %, date, reference and eyebrow |

`h1`–`h4` are display type by default — no component has to remember.

| Token | Clamp | Use |
|---|---|---|
| `display-2xl` | 38 → 62px | Homepage hero only |
| `display-xl`  | 32 → 48px | Sub-page heroes |
| `display-lg`  | 30 → 44px | Section headlines |
| `display-md`  | 22 → 28px | Card and panel headings |
| `display-sm`  | 18px | Dense headings |
| `lead`        | 17 → 19px | Hero and section sub-copy |
| `eyebrow`     | 11px / `0.16em` | Mono, uppercase, always saffron |

**Monospace is a signal, not a texture.** Anything a bidder might check — a quote, a
deadline, a tender reference, a BOQ line — is mono with `.tnum` so figures align in
columns. Prose is never mono.

Measure is capped at `max-w-measure` (64ch). Body copy never runs wider.

---

## 3. Spacing, shape, elevation

- **Section rhythm:** `py-section` (4.5rem) mobile, `py-section-lg` (7rem) desktop.
- **Shell:** `max-w-shell` (80rem), gutters `px-5 sm:px-8`.
- **Sidebar rail:** `w-rail` (15rem).
- **Radii are small on purpose** — `card` 4px, `panel` 6px, `chip` 2px. Sharp corners
  read as instrument; pill-shaped everything reads as consumer app.
- **Elevation is rare.** Structure is carried by hairlines, not shadows.
  `shadow-card` for panels, `shadow-raised` for menus, `shadow-deep` for the hero
  product panel, `shadow-cta` for saffron buttons only.

### The grid-of-hairlines pattern
The signature layout device across the whole site:

```html
<div class="grid grid-cols-3 gap-px bg-steel-200 border border-steel-200 rounded-panel overflow-hidden">
  <article class="bg-white p-6">…</article>
</div>
```

A 1px gap over a steel background produces true hairline dividers with no double borders
at any breakpoint. Used for feature grids, pricing, trust tiles, stat bars, the agent board.

---

## 4. Components

### Buttons — exactly three
| Class | Use |
|---|---|
| `.btn-primary` | Saffron fill. The money action. Max two per viewport |
| `.btn-secondary` | Navy fill. Confirmations that are not the money action |
| `.btn-ghost` / `.btn-ghost-dark` | Outline. Secondary navigation, light and dark grounds |

Sizes: `.btn-lg` (hero), `.btn-md` (default), `.btn-sm` (toolbars, tables).

### Surfaces
`.panel` (white, hairline, card shadow) · `.panel-flat` (no shadow) · `.panel-dark` (navy).

### Chips
`.chip-ok` `.chip-warn` `.chip-risk` `.chip-info` `.chip-live` — mono, uppercase, 2px radius.
Status is always a chip, never coloured body text.

### Data table
`.data-table` — mono uppercase head on `steel-100`, hairline rows, `saffron-50/50` row hover,
`.num` for right-aligned tabular figures. Dense by default: an operator comparing eight
tenders needs the deadlines in one column.

### App primitives (`components/layout/PageHeader.tsx`)
`PageHeader` · `PageBody` · `StatTile` · `Section` · `EmptyState`.

Every workspace screen opens identically: mono eyebrow → title → one line of orientation →
actions right. **`EmptyState` is never a shrug** — it always names the next action.

### Marketing primitives (`components/marketing/PageKit.tsx`)
`PageHero` · `SectionHead` · `CtaBand` · `Prose`. Plus `AuthShell` for the three auth screens,
so the brand ground never flips mid-signup.

---

## 5. Motion

Motion confirms an action or shows work happening. It never decorates.

| Pattern | Spec | Where |
|---|---|---|
| Hover lift | `.lift` — `translate3d(0,-2px,0)`, 200ms `cubic-bezier(.22,1,.36,1)` | Cards, tiles |
| Rule draw-in | width 0 → 100%, 300ms | Agent cards, phase tabs |
| Reveal on scroll | `.reveal-*` — 14px rise + fade, 700ms, threshold 0 / `-12%` margin | Sections, once only |
| Stagger | `.stagger` — 60ms per child, capped at 12 | Grids |
| Live pulse | `.dot-live` — expanding ring, 2s | **One element per live process. Never two** |
| Progress fill | `scaleX` transition, 300ms ease-out | Pipeline run, win rate |
| Panel entry | `animate-rise`, 500ms | Menus, agent brief, phase detail |
| Route change | `.page-enter` — opacity, 320ms | `PublicLayout`, keyed on pathname |
| Skeleton | `.skeleton` sweep, 1.6s | Any load over ~300ms |

**Rules**
- `prefers-reduced-motion: reduce` collapses everything to 0.01ms. Handled globally in
  `index.css` — components do not re-implement it.
- **Nothing bounces.** No spring easing, no scale-up on hover, no floating blobs.
- **Motion must never change layout.** See §7.
- **A pulse means *running*.** Eleven idle specialists get eleven static dots, not
  eleven pulsing ones — that is noise, not information.

### Staying at 60fps

Animate **`transform` and `opacity` only**. Both are composited; everything else costs
layout or paint on every frame. Measured on the homepage, these four changes took the
hero from 13 dropped frames in 90 to zero:

| Was | Now | Why |
|---|---|---|
| Progress bar `transition-[width]` | `scaleX()` | Width relayouts the bar *and its ancestors* every frame |
| All 11 rows re-rendered per 330ms tick | `memo` per row | Only two rows change per tick; React was doing 11 |
| `pulse-live` animating `box-shadow` | pseudo-element ring, transform + opacity | Shadow spread repaints the dot and its backdrop |
| `.btn` `transition-all` | named properties | `all` makes the browser watch every animatable property forever |

Two more standing rules:
- Full-bleed decorative grounds (`bg-grid-dark`, `bloom-saffron`) carry `.layer`, which
  promotes them so a viewport-sized gradient is not re-rasterised whenever anything above
  it moves.
- Anything re-rendering on a timer carries `.contain-paint`.

Verify with the frame-interval probe rather than by eye: median ≈16.7ms, **p95 under
18ms, zero frames over 20ms**, both idle and while scrolling.

---

## 6. Interaction rules

- **Focus:** one treatment everywhere — 2px saffron outline, 2px offset. Never removed.
  This is a tool used on deadline day with a keyboard.
- **Contrast:** body text ≥ 4.5:1, large text ≥ 3:1. White-on-saffron uses `saffron-600`.
- **Loading:** skeleton rows that match the real row height, so nothing jumps on arrival.
- **Failure:** every fetch uses `Promise.allSettled` and renders a retry state. A failing
  stats call must never leave the screen on skeletons forever.
- **Empty:** name the next action and link to it.
- **Numbers we do not have:** render nothing. `OutcomeStrip` hides itself when every stat
  is `null`. On a product whose promise is that it does not fabricate, an invented counter
  on the homepage is the most expensive possible contradiction.

---

## 7. Two layout-stability rules

Both were live bugs. Both are easy to reintroduce.

**1. Sticky headers do not change height.**
The public header used to shrink 68px → 56px on scroll. That re-laid out the page beneath
the scroll position, moved it back across the threshold, and toggled again — the page
visibly juddered. Only `border` and `shadow` change now. `backdrop-blur` was removed for
the same reason: blurring a full-width bar over a gradient hero repaints every scroll frame.

**2. Cells that change content get a reserved width.**
In the hero run panel each row's status cycles `queued` → `analysing…` → the real result.
Letting the cell size to its content resized the name column on every tick, which read as
the panel shaking. The status cell is now a fixed `w-[8.75rem]`, weight never changes with
state, and counters use `.tnum` inside fixed-width spans.

Anything that re-renders on a timer also gets `.contain-paint` (`contain: layout paint`) so
its reflow cannot escape into the rest of the page.

---

## 8. Voice

Aggressive, confident, specific. Never soft, never cute.

- "Win more government tenders. **Stop losing on technicalities.**"
- "You are not losing tenders on capability. You are losing them on paperwork."
- "A comparable human bid team costs ₹4–6 lakh a month."
- "Every loss has an owner." — each of the eleven prevents one *named* way of losing.

**Never** claim a win rate, a customer count or a usage figure we cannot substantiate.
Concrete and true beats impressive and vague, every time, for this buyer.

---

## 9. Page inventory

**Public:** `/` · `/features` · `/how-it-works` · `/pricing` · `/about` · `/contact` ·
`/privacy` · `/terms` · 404
**Auth:** `/login` · `/signup` · `/verify-email`
**Workspace:** `/app/overview` (Command Centre) · `/app/bid` · `/app/analysis` ·
`/app/bids` · `/app/vault` · `/app/profile` · `/app/dashboard` (The AI Team) · `/app/admin/users`

The customer-facing roster is **eleven**. `it-support` exists in the registry as an internal
platform agent and is filtered out of the AI Team screen — every surface, marketing included,
says eleven, and the two must not disagree.
