# Nexus UI - the CoNexus component library

Every screen in the web app (`frontend/`) is built only from this library. Import from `@ui`:

```tsx
import { Button, Card, ClauseCard, PriceChart, StatusBadge } from "@ui";
```

Live gallery with every component and variant: **http://localhost:8000/ui** (or `/ui` on the dev server).

## Structure

```
frontend/src/ui/
  tokens.css        design tokens: colour, type, space, radius (light + dark)
  styles.css        component styles; colours come only from tokens
  primitives.tsx    general components
  domain.tsx        contract-negotiation components
  workspace.tsx     workspace patterns: breadcrumbs, next action, table toolbar, steps, activity feed
  overlay.tsx       Dialog, Toast
  charts/           PriceChart, MetricBars, ThresholdChart (Recharts)
  AppShell.tsx      top navigation (Work / Reports / Learn), create action, account menu, mobile task menu
  index.ts          public API + font loading
```

## Design decisions

| Decision | Why |
|---|---|
| Blue-grey neutrals, one Ocean (teal) accent; one production palette | A quiet legal-operations workspace; the accent marks actions and focus only. Other palettes are a preview under Learn → Colour themes |
| Status colours (good / warning / serious / critical) are reserved | State always comes with an icon or text label too, never colour alone |
| Plus Jakarta Sans headings, Inter body, JetBrains Mono for machine-exact values | Clause refs (§ 6), hashes, money and net-days read as exact data |
| Every colour is a CSS token, redefined for dark mode | Three theme states work: light, dark and "system" (no `data-theme`) |
| Charts use validated categorical slots (blue = us, orange = them) | Policy lines (floor, concession limit) are dashed muted ink, never a series colour; one y-axis |
| Fonts bundled via `@fontsource` | Works offline (college lab, viva room) |

## Components

**Layout** · `Stack`, `Row`, `Grid`, `AppShell`, `PageHeader`, `Breadcrumbs`

**Workspace patterns** · `NextAction` (the one next step and its owner), `Toolbar` + `FilterChip` + `SortSelect` + `ResultCount`
(the standard table toolbar), `Steps` (multi-step forms), `ActivityFeed` (plain-language actors: CoNexus, a person, Customer, System)

**Primitives** · `Button` (primary, secondary, ghost, success, danger; sm/md/lg; loading), `Badge` (6 tones, dot, outline),
`Card` (title, actions, flush, critical tone), `Stat`, `Table` (typed columns, numeric alignment, keyboard-clickable rows, `cards` = labelled cards below 640px),
`Tabs`, `Segmented`, `ChoiceGroup`, `Field`, `Input`, `Select`, `Textarea`, `Range`, `Alert`, `Spinner`, `Skeleton`,
`EmptyState`, `KeyValue`, `Divider`, `Legend`

**Overlays** · `Dialog` (native `<dialog>`, used for confirmations), `ToastProvider` + `useToast()`

**Domain** (specific to contract negotiation)

| Component | What it shows |
|---|---|
| `StatusBadge` | Contract stage, one vocabulary everywhere (`STAGE`): Ready to negotiate, Negotiating, Needs review, Sent to sign, Closed |
| `RiskBadge` | Clause risk level plus a "Needs human" flag |
| `ScoreMeter` | Risk score 0-1 with the escalation threshold marked |
| `ClauseCard` | Clause text, § ref, risk, reasons, suggested redline, review state |
| `RedlineDiff` | Word-level legal redline (deletions struck, insertions underlined); falls back to a block replacement when the clause is rewritten |
| `NegotiationThread` | Offers and replies as a conversation with term chips |
| `PriceChart` | Our and their offers per round against the floor and concession limit |
| `AuditTimeline` | Hash-chained decisions with agent, action, rationale and hash |
| `HashChip` | Truncated SHA-256 with copy-to-clipboard |
| `DealStepper` | Analyze, Risk review, Negotiate, Legal review, E-signature |
| `SignatureStamp` | Envelope id and final terms once sent for signature |

## Adding a component

1. Add styles to `styles.css` using only tokens from `tokens.css` (no literal colours).
2. Add the component to `primitives.tsx` or `domain.tsx` and export it from `index.ts`.
3. Add a section to `src/pages/Gallery.tsx` showing its variants.
4. Check it in light and dark mode and at phone width.

## Product rules (from the frontend design plan)

- Work first: Home, Contracts and the Review queue are the main navigation; Reports hold Portfolio and Audit history;
  research, demo and developer pages live under **Learn**.
- One primary action per area. The global primary action is **Create contract**.
- Operational screens use borders and quiet surfaces: no gradients, glow, count-up numbers or ambient animation.
  Brand gradients stay on the public landing and sign-in pages.
- Status is words plus icon plus colour, never colour alone. "Sent to sign" until a real e-signature provider confirms.
- Every list has an empty, loading and error state that says what happened and what to do next.
- Demo data is labelled as demo (sample contracts, the demo workspace banner, the simulated buyer).
