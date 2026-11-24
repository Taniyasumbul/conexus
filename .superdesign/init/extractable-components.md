# Extractable components

## AppShell

- Source: `frontend/src/ui/AppShell.tsx`
- Category: layout
- Description: authenticated top navigation and responsive mobile navigation.
- Extractable props: user, inboxCount, notification count/content, active route, sign-out handler.
- Hardcoded: logo, primary navigation labels, research-navigation grouping.

## PageHeader

- Source: `frontend/src/ui/primitives.tsx`
- Category: layout
- Description: standard page title, description, context label, and actions.
- Extractable props: eyebrow, title, description, actions.

## Card

- Source: `frontend/src/ui/primitives.tsx`
- Category: basic
- Description: standard content container with heading and actions.
- Extractable props: title, subtitle, actions, tone, flush, flat.

## Button

- Source: `frontend/src/ui/primitives.tsx`
- Category: basic
- Description: semantic action button with clear variants and loading state.
- Extractable props: variant, size, icon, loading, disabled, block.

## DataTable

- Source: `frontend/src/ui/primitives.tsx`
- Category: basic
- Description: typed table with keyboard-accessible row navigation.
- Extractable props: columns, rows, row key, row action, empty state.

## StatusBadge and DealStepper

- Source: `frontend/src/ui/domain.tsx`
- Category: basic
- Description: product-wide contract lifecycle language and status rendering.
- Extractable props: status, escalation state, workflow stage.

## DecisionPanel

- Source: `frontend/src/pages/shared.tsx`
- Category: basic
- Description: legal approval/rejection interaction with audit note and confirmation.
- Extractable props: contract ID, escalation, callback, reviewer permissions.
