# Perpetual Analyst — UI Design Concept

**Version:** 1.0 · **Status:** Concept · **Surface:** Web (desktop-first, ≥1440px reference frame)

Perpetual Analyst is a continuously-running intelligence dashboard for a single analyst persona. It ingests sources around the clock, synthesizes them into briefings, tracks topic-level signal, and maintains falsifiable hypotheses with confidence scores. The UI's job is to let an analyst absorb the state of the world in under a minute, then drill into any thread without losing orientation.

---

## 1. Design Thesis

**"A terminal that reads like a briefing."**

The design borrows the density and darkness of financial terminals (Bloomberg-adjacent) but rejects their hostility. Every module answers one analyst question — *What happened? What's moving? What do we believe? What do we remember?* — and the visual system is subordinated to that reading order. Nothing on the screen is decorative; every sparkline, badge, and count encodes state.

Three commitments follow from this:

1. **Glanceability over completeness.** Every module is a summary with a `View all` escape hatch. The dashboard never tries to be the full record.
2. **Time is the organizing axis.** Relative timestamps ("2h ago"), a date-range scope in the header, sparklines with 7d deltas, and prediction horizons all keep the analyst oriented in time.
3. **Confidence is a first-class citizen.** Predictions carry explicit confidence percentages and status states. The system shows its epistemic posture rather than asserting flat facts.

---

## 2. Layout & Information Architecture

### 2.1 Frame

A fixed three-part frame:

```
┌──────────┬──────────────────────────────────────────────────────┐
│          │  Top bar: search (⌘K) · date range · alerts · user   │
│  Sidebar ├──────────────────────────────────────────────────────┤
│  (nav +  │  Row 1: Daily Briefing (hero, ~55%) │ 4 KPI cards    │
│  system  ├──────────────────────────────────────────────────────┤
│  status) │  Row 2: Story Timeline │ Signal Chart │ Sources      │
│          │         + Top Topics   │ + Predictions│ + Memory     │
└──────────┴──────────────────────────────────────────────────────┘
```

- **Sidebar (~215px, collapsible).** Seven destinations in workflow order: Dashboard, Topics, Sources, Memory, Reports, Predictions, Settings. Active item gets a filled dark-elevated pill. System status (Operational + last-updated) is pinned to the bottom — infrastructure trust lives quietly in the chrome, not the content area.
- **Top bar.** Global search with `⌘K` affordance, a date-range picker that scopes the whole dashboard, notification bell with unread dot, and identity (name + role).
- **Content grid.** A 12-column grid resolving into three content columns below the hero row. Columns map to the reading order: *narrative* (left: timeline, top topics) → *quantitative* (center: signal chart, predictions) → *provenance & memory* (right: sources, entities, themes).

### 2.2 Module inventory

| Module | Question it answers | Key affordances |
|---|---|---|
| Daily Briefing | "What's the headline?" | Prose synthesis, continuous-update indicator, next-brief countdown, ambient globe visual |
| KPI cards ×4 | "Is the system healthy and is the world moving?" | Big number, 7d delta (colored), sparkline |
| Story Timeline | "What happened, in order?" | Relative timestamps, category icon + tag per event, full-timeline CTA |
| Signal Intensity | "Which topics are heating up?" | Multi-series area chart, topic legend, 7D/30D/90D range toggle, view-by selector |
| Hypotheses / Predictions | "What do we believe and how strongly?" | Status pill (Rising / Watch / Stable / Confirmed), confidence % + band (High/Medium/Low), time horizon |
| Top Topics | "What's ranked highest right now?" | Score, trend sparkline, rank-change arrows |
| Recent Sources | "Where is this coming from?" | Favicon, domain, recency, type badge (Article / Newsletter / Paper) |
| Memory & Insights | "What does the system remember?" | Entity mention counts, recurring-theme counts, total sources remembered |

---

## 3. Color System

### 3.1 Foundations (dark theme, single theme by design)

| Token | Approx. value | Use |
|---|---|---|
| `bg/base` | `#07090D` | App canvas, sidebar |
| `bg/surface` | `#0D1117` | Cards, modules |
| `bg/elevated` | `#151B23` | Nested chips, active nav pill, table row hover |
| `border/subtle` | `#1E2630` | 1px card borders, dividers |
| `text/primary` | `#F2F5F8` | Headings, key numbers |
| `text/secondary` | `#8A94A3` | Body, metadata, timestamps |
| `text/tertiary` | `#5A6472` | Placeholder, disabled |

The surface hierarchy is intentionally shallow — two elevation steps above base, no drop shadows. Depth is communicated by border + fill contrast, keeping the field flat and calm so that *color means data*.

### 3.2 Semantic & categorical accents

| Token | Approx. value | Meaning |
|---|---|---|
| `accent/primary` | `#2DE0A6` (teal-green) | Brand, positive deltas, "operational," primary sparklines |
| `signal/ai` | `#2DE0A6` | AI & LLMs topic series |
| `signal/policy` | `#3B82F6` (blue) | Policy topic series |
| `signal/markets` | `#8B5CF6` (violet) | Markets topic series |
| `signal/research` | `#EAB308` (amber) | Research topic series |
| `status/negative` | `#EF4444` | Negative deltas, falling ranks |
| `status/watch` | `#F59E0B` | Watch-state predictions |

Rules:

- **Categorical colors are contracts.** A topic keeps its hue everywhere — timeline tags, chart series, legend, top-topics sparklines. Cross-module color consistency is what lets the analyst pattern-match at a glance.
- **Green/red is reserved for direction**, never for topics, so delta semantics stay unambiguous.
- Accents appear at low luminance-area: thin strokes, small pills, sparklines, soft area-fill gradients (~15% opacity fading to transparent). Large fields stay neutral.

---

## 4. Typography

Single sans family (Inter or equivalent grotesque) across the product; hierarchy comes from size, weight, and color rather than face changes — appropriate for a data-dense tool where type must disappear into the reading.

| Role | Size / weight | Notes |
|---|---|---|
| KPI numerals | 32–36px / 700 | Tabular figures mandatory |
| Module titles | 15–16px / 600 | e.g. "Story Timeline," "Signal Intensity Over Time" |
| Body / list items | 13–14px / 500 | Event titles, source names, prediction statements |
| Metadata | 12px / 400, `text/secondary` | Timestamps, domains, delta captions |
| Badges & tags | 11px / 500 | Sentence case, no all-caps shouting |

Numerals are the loudest voice on the page by design: the type scale gives the four KPI figures roughly 2.5× the size of anything else, making the health-check the sub-second read.

---

## 5. Components

### 5.1 Cards
16px radius, `bg/surface` fill, 1px `border/subtle`, 20–24px internal padding. Every card follows the same anatomy: title (left) · action link "View all" (right) · content. Uniform anatomy makes the dashboard scannable as a grid of answers.

### 5.2 Status pills
Rounded-full, tinted background at ~12% of the semantic color, matching text, optional leading glyph (↑ arrow, ⊙ watch, ✓ check). Four prediction states: **Rising** (green), **Watch** (amber), **Stable** (blue-gray), **Confirmed** (green + check). Pills are the only place saturated fills appear.

### 5.3 Sparklines
44–90px wide, 1.5px stroke, no axes. They appear in KPI cards, Top Topics rows, and implicitly set the visual rhythm: *every number gets a shape.* A number without trend context is treated as an incomplete component.

### 5.4 Timeline
Left rail of relative timestamps + a vertical connector, category-colored icon tiles (rounded 8px, tinted fill), two-line entries (bold title, secondary summary), and a category tag chip. Chronology reads top-down, newest first.

### 5.5 Chart module
Stacked/overlaid area series with smooth interpolation, gradient fills fading to transparent, dot legend beneath, segmented range control (7D/30D/90D) and a "View by" dropdown in the header. Gridlines are near-invisible; the series shapes carry the reading.

### 5.6 Source rows
Favicon tile (rounded 8px) · title · domain + recency · trailing type badge. Provenance is always double-encoded: visual (favicon) + textual (domain).

### 5.7 Predictions table
Statement + topic tag · status pill · confidence (% + verbal band stacked) · horizon. Sortable column headers. The verbal band (High/Medium/Low) hedges the false precision of the percentage — a deliberate epistemic-honesty detail.

---

## 6. Motion & Live State

The product's premise is *perpetual* operation, so liveness is signaled continuously but quietly:

- Pulsing green dot + "Updated continuously" in the briefing header; countdown to next brief ("Next brief in 3h 42m").
- "Last updated: 2m ago" under the sidebar status.
- Notification dot on the bell.
- Recommended motion: sparklines and chart areas draw-in on load (300–400ms ease-out); new timeline items slide in from top with a brief accent flash; number changes tick via count-up. All motion under 400ms, `prefers-reduced-motion` fully respected (fade-only fallback).

No ambient animation beyond the status pulse — a monitoring tool that fidgets erodes trust.

---

## 7. Interaction Notes

- **Search-first navigation.** `⌘K` command palette over topics, sources, and entities; the search field advertises the shortcut.
- **Scoped time.** The header date range re-scopes every module simultaneously; per-module toggles (7D/30D/90D) override locally.
- **Progressive disclosure.** Dashboard → module "View all" → dedicated section page (mirrored in sidebar nav). The dashboard is a table of contents, not a terminus.
- **Hover affordances (recommended):** chart crosshair with per-series tooltip; timeline items and source rows elevate to `bg/elevated`; entity/theme counts open filtered views on click.

---

## 8. Accessibility

- Text contrast: primary text ≥ 12:1, secondary ≥ 4.5:1 on surfaces.
- Categorical series are never distinguished by hue alone in critical reads — legend labels, tags, and tooltips carry names; consider dash patterns as a colorblind-safe fallback in the chart.
- Delta direction is triple-encoded: sign (+/−), arrow glyph, and color.
- Full keyboard path: visible focus rings (2px `accent/primary` at 60%), `⌘K` palette, logical tab order following the reading columns.
- Live regions (`aria-live="polite"`) for briefing updates and KPI ticks.

---

## 9. Responsive Strategy

- **≥1440px:** three-column grid as specified.
- **1024–1439px:** sidebar collapses to icon rail; right column (Sources / Memory) drops below the center column.
- **<1024px:** single column in reading order — Briefing → KPIs (2×2) → Timeline → Chart → Predictions → Sources → Memory. Chart gains horizontal scroll rather than compressing below legibility.

---

## 10. Anti-goals

- No light theme in v1 — the terminal identity and the low-luminance data-encoding rules are built for dark.
- No skeuomorphic depth, glassmorphism, or shadow stacks.
- No decorative illustration beyond the briefing's ambient globe, which doubles as a "global ingestion" metaphor and stays behind text at low opacity.
- No red/green reuse for anything other than direction/health.
- No module without an exit — every summary links to its full record.
