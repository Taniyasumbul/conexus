# Shared components

## `frontend/src/ui/primitives.tsx`

Shared product primitives: layout (`Stack`, `Row`, `Grid`), actions (`Button`), data display (`Card`, `Table`, `Badge`, `Stat`), forms, tabs, alerts, empty states, and feedback. This is the primary reusable component source; use it rather than adding page-local controls.

Key exports: `Button`, `Card`, `PageHeader`, `Table`, `Tabs`, `Segmented`, `Field`, `Input`, `Select`, `Textarea`, `Alert`, `EmptyState`, `Skeleton`, `SaveBar`, `Company`, `Avatar`.

## `frontend/src/ui/domain.tsx`

Contract-domain shared components: workflow status, risk assessment, redline and document rendering, negotiation timeline, pricing, audit history, and signature state.

Key exports: `StatusBadge`, `RiskBadge`, `ClauseCard`, `RedlineDiff`, `DealStepper`, `NegotiationThread`, `AuditTimeline`, `PriceChart`, `ContractFingerprint`, `SignatureStamp`.

## `frontend/src/ui/overlay.tsx` and `notifications.tsx`

Shared modal/dialog, toast, and notification interactions.

## Component rules

- All shared UI is exported through `frontend/src/ui/index.ts` and imported through `@ui`.
- Visual values must use CSS tokens from `tokens.css`; page components must not introduce new hard-coded colors.
- Every new reusable component needs gallery coverage in `frontend/src/pages/Gallery.tsx` and light/dark/mobile checks.
