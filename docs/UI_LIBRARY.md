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
  overlay.tsx       Dialog, Toast
  charts/           PriceChart, MetricBars, ThresholdChart (Recharts)
  AppShell.tsx      sidebar navigation, theme switch, mobile drawer
  index.ts          public API + font loading
```

## Design decisions

| Decision | Why |
|---|---|
| Ink-navy neutrals with a slight blue bias, one blue accent | Calm "legal ledger" control room; the accent marks actions only |
| Status colours (good / warning / serious / critical) are reserved | State always comes with an icon or text label too, never colour alone |
| Space Grotesk headings, Inter body, JetBrains Mono for machine-exact values | Clause refs (§ 6), hashes, money and net-days read as exact data |
| Every colour is a CSS token, redefined for dark mode | Three theme states work: light, dark and "system" (no `data-theme`) |
| Charts use validated categorical slots (blue = us, orange = them) | Policy lines (floor, concession limit) are dashed muted ink, never a series colour; one y-axis |
| Fonts bundled via `@fontsource` | Works offline (college lab, viva room) |

## Components

**Layout** · `Stack`, `Row`, `Grid`, `AppShell`, `PageHeader`

**Primitives** · `Button` (primary, secondary, ghost, success, danger; sm/md/lg; loading), `Badge` (6 tones, dot, outline),
`Card` (title, actions, flush, critical tone), `Stat`, `Table` (typed columns, numeric alignment, keyboard-clickable rows),
`Tabs`, `Segmented`, `ChoiceGroup`, `Field`, `Input`, `Select`, `Textarea`, `Range`, `Alert`, `Spinner`, `Skeleton`,
`EmptyState`, `KeyValue`, `Divider`, `Legend`

**Overlays** · `Dialog` (native `<dialog>`, used for confirmations), `ToastProvider` + `useToast()`

**Domain** (specific to contract negotiation)

| Component | What it shows |
|---|---|
| `StatusBadge` | Contract stage: Analyzed, Negotiating, Needs human, Signed, Closed |
| `RiskBadge` | Clause risk level plus a "Needs human" flag |
| `ScoreMeter` | Risk score 0-1 with the escalation threshold marked |
| `ClauseCard` | Clause text, § ref, risk, reasons, suggested redline, review state |
| `RedlineDiff` | Word-level legal redline (deletions struck, insertions underlined); falls back to a block replacement when the clause is rewritten |
| `NegotiationThread` | Offers and replies as a conversation with term chips |
| `PriceChart` | Our and their offers per round against the floor and concession limit |
| `AuditTimeline` | Hash-chained decisions with agent, action, rationale and hash |
| `HashChip` | Truncated SHA-256 with copy-to-clipboard |
| `DealStepper` | Ingest, Risk review, Negotiate, Human gate, Signed |
| `SignatureStamp` | Envelope id and final terms once sent for signature |

## Adding a component

1. Add styles to `styles.css` using only tokens from `tokens.css` (no literal colours).
2. Add the component to `primitives.tsx` or `domain.tsx` and export it from `index.ts`.
3. Add a section to `src/pages/Gallery.tsx` showing its variants.
4. Check it in light and dark mode and at phone width.
