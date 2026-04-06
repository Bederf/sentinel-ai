---
title: "uncodixify.md — UI Generation Rules for AI Systems"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# uncodixify.md — UI Generation Rules for AI Systems

> **Purpose:** This file defines strict UI generation rules for AI systems. Its job is to prevent the typical AI-generated dashboard aesthetic and force the model to generate interfaces that look like professional software products — Grafana, Linear, GitHub, Vercel — not Codixify template dumps.

---

## 1. Core Design Principles

Every generated interface must follow these non-negotiable principles:

1. **Density over decoration.** Show more information in less space. White space is not a feature — it is wasted viewport.
2. **Function over form.** Every pixel must serve a purpose. If a visual element does not help the user make a decision or take an action, remove it.
3. **Hierarchy through typography, not color.** Use font weight, size, and opacity to establish information hierarchy. Do not use background colors to create visual sections.
4. **Monochrome first.** Design the interface in grayscale. Add color only where it encodes meaning (status, severity, trend direction). If you can remove a color and lose no information, remove it.
5. **Professional restraint.** The interface should look like it was built by a team that ships to thousands of paying users, not generated in a prompt.

---

## 2. Layout Rules

### Grid and Structure
- Use CSS Grid or Flexbox. Never use absolute positioning for layout.
- Maximum content width: `1440px` centered. Sidebar excluded from max-width.
- Minimum touch target: `32px` height for interactive elements.
- Consistent gutter: `12px` or `16px`. Pick one per interface and do not mix.

### Spacing
- Use a 4px base unit. All spacing values must be multiples of 4: `4, 8, 12, 16, 20, 24, 32, 40, 48`.
- Never use arbitrary spacing values like `13px`, `17px`, or `23px`.
- Section gaps: `24px` between major sections, `12px` between related items, `8px` between tightly coupled elements.

### Responsive Behavior
- Collapse sidebar to icon-only below `1024px`. Hide below `768px` with hamburger toggle.
- Stack cards vertically below `768px`. Two-column minimum at `1024px`.
- Tables become card lists on mobile. Never horizontally scroll a table.

---

## 3. Component Rules

### Tables
- Default to tables for tabular data. Not cards. Not lists. Tables.
- Sticky header row. Sortable columns indicated by a subtle chevron, not a full icon.
- Row hover: `background: rgba(255, 255, 255, 0.03)` — barely visible, not a spotlight.
- Zebra striping: do not use it. Use border-bottom `1px solid` at `8%` opacity instead.
- Cell padding: `8px 12px`. Compact mode: `4px 8px`.
- Right-align numeric columns. Left-align text. Center only single-character status indicators.

### Cards
- Cards are for heterogeneous content only (mixed media, varied layouts per item). If every card has the same structure, use a table.
- No drop shadows. Border: `1px solid` at `10%` opacity.
- No border-radius greater than `8px`. Prefer `4px` or `6px`.
- Card padding: `16px`. No internal dividers unless content groups are semantically distinct.

### Buttons
- Primary action: filled, single per visible viewport section.
- Secondary actions: ghost (border only) or text-only.
- Destructive actions: red text or red ghost border. Never a filled red button for inline actions.
- Button height: `32px` default, `28px` compact, `36px` prominent.
- Button padding: `8px 12px` minimum. Icon-only buttons are square.
- No gradients. No shadows. No rounded-pill shapes (`border-radius: 9999px` is banned).

### Forms
- Label above input, not beside it (wastes horizontal space on narrow viewports).
- Input height: `32px`. Textarea minimum height: `80px`.
- Border: `1px solid` at `15%` opacity. Focus ring: `2px solid` accent color.
- Error state: red border + red helper text below. No error icons inside the input.
- Group related fields. Use `fieldset` semantics with a visible legend.

### Charts
- Use for time-series, distributions, and comparisons only. Do not chart a single number.
- Axis labels are mandatory. No chart without labeled axes.
- Gridlines: dotted, `5%` opacity. Major gridlines only — no minor gridlines.
- Legend: inline above chart or to the right. No floating legend boxes.
- Tooltip: appears on hover with exact value. No persistent annotation bubbles.
- Maximum 5 series per chart. Beyond that, use small multiples.
- Prefer line charts for time-series, bar charts for comparisons, and heatmaps for density. Avoid pie charts, 3D charts, and gauge charts.

### Navigation
- Sidebar for primary navigation. Top bar for context (user, search, notifications).
- Active state: background highlight + left border accent. Not bold text alone.
- Nesting: maximum 2 levels. If you need 3, restructure your information architecture.
- Breadcrumbs for deep navigation. Slash-separated, not chevron-separated.

---

## 4. Visual Style Rules

### Typography
- System font stack: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`.
- Monospace for data values, codes, IDs: `'JetBrains Mono', 'Fira Code', 'SF Mono', monospace`.
- Maximum 3 font sizes per view. Suggested scale: `12px`, `13px`, `14px` body; `16px`, `18px` headings; `11px` captions/labels.
- Line height: `1.4` for body, `1.2` for headings, `1.6` for long-form text.
- No uppercase text except for tiny labels (`11px`, `letter-spacing: 0.05em`).
- Font weight: `400` body, `500` emphasis, `600` headings. Do not use `700` or `800`.

### Colors — Dark Mode (Default)
```
Background:       #0a0a0a (page) / #111111 (surface) / #1a1a1a (elevated)
Border:           rgba(255, 255, 255, 0.08)
Text primary:     rgba(255, 255, 255, 0.87)
Text secondary:   rgba(255, 255, 255, 0.55)
Text tertiary:    rgba(255, 255, 255, 0.35)
Accent:           #3b82f6 (blue) — used sparingly
```

### Colors — Light Mode
```
Background:       #ffffff (page) / #f8f8f8 (surface) / #f0f0f0 (elevated)
Border:           rgba(0, 0, 0, 0.08)
Text primary:     rgba(0, 0, 0, 0.87)
Text secondary:   rgba(0, 0, 0, 0.55)
Text tertiary:    rgba(0, 0, 0, 0.35)
Accent:           #2563eb (blue)
```

### Status Colors
```
Healthy / Success:   #22c55e (green)
Warning:             #eab308 (yellow)
Critical / Error:    #ef4444 (red)
Info / Neutral:      #3b82f6 (blue)
Inactive / Disabled: rgba(255, 255, 255, 0.25)
```

Status colors are used for: badges, dot indicators, border-left accents, and sparkline trends. Never as background fills for entire cards or sections.

### Icons
- Use Lucide icons (or equivalent thin-stroke icon set). No filled/solid icon styles.
- Icon size: `16px` inline, `20px` in buttons, `24px` standalone.
- Icon color: inherit from text. Do not colorize icons unless they represent status.
- No emoji as icons. No decorative icons. Every icon must have a functional purpose.

---

## 5. Strictly Banned Patterns

These patterns are the hallmarks of AI-generated UI. Never use them:

| Banned Pattern | Why | Use Instead |
|---|---|---|
| Gradient backgrounds | Decorative, dates quickly | Flat solid colors |
| Card grids for KPIs | Wastes space, looks like a template | Inline stat row or compact header bar |
| Large circular progress indicators | Novelty UI, not information-dense | Inline percentage + progress bar |
| Colored section backgrounds | Creates "lego block" aesthetic | Typography hierarchy, subtle borders |
| Drop shadows on cards | Skeuomorphic, adds visual noise | `1px` border at low opacity |
| Rounded pill buttons | Consumer app aesthetic | `4px` border-radius buttons |
| Icon + large number + label card | The "dashboard starter kit" pattern | Table row or inline stat |
| Full-width hero banners | Marketing, not software | Jump straight to content |
| Skeleton loaders everywhere | Over-engineering for generated UI | Simple spinner or "Loading..." text |
| Animated counters / number tickers | Gratuitous motion | Static rendered value |
| Glassmorphism / backdrop-blur | Performance cost, no information value | Solid background |
| Excessive border-radius (>12px) | Toy-like appearance | `4px`–`8px` border-radius |
| Rainbow status colors | Cognitive overload | 4 status colors maximum |
| Floating action buttons | Mobile pattern forced onto desktop | Inline button in context |
| Accordion for <5 items | Hides information unnecessarily | Show all items |
| Toast notifications for expected actions | Noise | Inline confirmation |

---

## 6. Panels vs Cards — Decision Framework

Use this decision tree:

```
Is the content tabular (same fields per item)?
  YES → Use a table. Stop.
  NO  → Continue.

Does the content have mixed media (image + text + actions)?
  YES → Use cards in a grid. Stop.
  NO  → Continue.

Is it a single data group with a title?
  YES → Use a panel (bordered section with heading). Stop.
  NO  → Continue.

Is it a key-value summary?
  YES → Use a definition list or two-column layout inside a panel. Stop.
  NO  → Use a panel. When in doubt, panel > card.
```

### Panel Rules
- Border: `1px solid` at `8%` opacity. No background fill.
- Heading: `14px`, `font-weight: 500`. Flush left, no centering.
- Padding: `16px`. Content starts immediately below heading.
- No collapse/expand unless panel contains >20 items.

### Card Rules
- Maximum 4 cards per row. 3 is preferred.
- All cards in a row must be equal height (use `align-items: stretch`).
- No nested cards. A card inside a card is a layout failure.

---

## 7. Color Selection Rules

### Semantic Color Assignment
Colors encode exactly four things. Nothing else.

1. **Status** — healthy (green), warning (yellow), critical (red), neutral (blue)
2. **Trend direction** — up (green), down (red), flat (grey)
3. **Interactive state** — hover, focus, active, disabled
4. **Data series differentiation** — in charts only, max 5 distinct hues

### Rules
- No decorative color. If removing the color loses no meaning, remove it.
- Background colors for sections: banned. Use borders and spacing.
- Accent color (blue): links, primary buttons, active nav items, focus rings. That's it.
- Do not use brand colors for UI chrome. Brand goes in the logo, nowhere else.
- Ensure `4.5:1` contrast ratio minimum for text. `3:1` minimum for large text and UI elements.

---

## 8. Monitoring / Operations Mode

When generating interfaces for monitoring, operations, or control systems (BMS dashboards, server monitoring, network operations), apply these additional rules:

### Data Density
- Target: 40+ data points visible without scrolling on a `1920×1080` viewport.
- Use compact tables with `4px 8px` cell padding.
- Inline sparklines (height: `20px`) beside numeric values for trend context.
- Status dots (`8px` circles) instead of status badges for space efficiency.

### Real-Time Indicators
- Subtle pulse animation (`opacity: 0.5 → 1.0`, 2s cycle) on live values only. No other animations.
- "Last updated" timestamp in the header, not per-widget.
- Stale data (>5min): dim text to tertiary opacity. Do not hide it.

### Alarm / Alert Hierarchy
- Critical: red left-border (`3px solid #ef4444`) + row background `rgba(239, 68, 68, 0.08)`.
- Warning: yellow left-border (`3px solid #eab308`). No background change.
- Info: no visual emphasis. Logged, not displayed prominently.
- Alarm count in nav/header: badge with count. Red badge for critical only.

### Control Surfaces
- Write/control actions must be visually distinct from read/display elements.
- Setpoint inputs: inline number input with unit label. No slider unless range is meaningful.
- Command buttons: ghost style with confirmation step. Never one-click destructive.
- Lock/unlock toggle for manual override: visible state indicator, not just a button.

---

## 9. Standard Application Mode

When generating interfaces for standard applications (CRUD, settings, user management, configuration), apply these rules:

### Forms and Inputs
- Single-column forms for creation/editing. Two-column only for settings pages with many fields.
- Save button: bottom-right of form, sticky if form scrolls. Ghost "Cancel" beside it.
- Validation: inline, on blur. Show error below field immediately — do not wait for submit.
- Success: redirect or inline "Saved" text that fades after 2 seconds. No toast.

### Lists and Selection
- Checkbox multi-select with bulk action bar that appears on selection.
- Single-select: radio buttons for <6 options, dropdown for 6+.
- Search/filter: top of list, full-width input. Filter chips below it for active filters.
- Empty state: single line of grey text. No illustrations. No call-to-action buttons in empty states.

### Detail Views
- Left column: primary content (70% width). Right column: metadata and actions (30% width).
- Tabs for detail sections. Maximum 5 tabs. If more, use a vertical nav within the detail view.
- Back navigation: breadcrumbs, not a back arrow button.

---

## 10. Decision Rules — When in Doubt

Use these tiebreakers when you are unsure:

| Decision | Default Choice |
|---|---|
| Table vs Cards | Table |
| Border vs Shadow | Border |
| Inline vs Modal | Inline |
| Show vs Hide | Show |
| Text vs Icon | Text (add icon only if space-constrained) |
| Color vs No color | No color |
| Animation vs Static | Static |
| Custom component vs Native HTML | Native HTML |
| Dark mode vs Light mode | Dark mode |
| Compact vs Spacious | Compact |

---

## 11. Final Instruction

When generating UI, ask yourself before every element: **"Would Grafana, Linear, or GitHub do this?"**

If the answer is no, do not do it.

If you catch yourself generating a grid of colorful KPI cards with large numbers and rounded corners, stop. Delete it. Start over with a table.

The goal is not to make something that looks "nice" or "modern." The goal is to make something that a facility manager, engineer, or operator can use for 8 hours a day without fatigue — something that communicates information efficiently and stays out of the way.

Build tools, not posters.
