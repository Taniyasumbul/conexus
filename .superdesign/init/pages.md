# Page dependency map

## `/` — Overview

- `frontend/src/pages/Overview.tsx`
  - `frontend/src/ui/domain.tsx` (AgentNetwork, StatusBadge)
  - `frontend/src/ui/primitives.tsx` (Card, Table, Stat, EmptyState, Button)
  - `frontend/src/lib/api.ts`, `hooks.ts`, `auth.tsx`
  - `frontend/src/pages/shared.tsx` (error state)

## `/contracts` — Contract repository

- `frontend/src/pages/Contracts.tsx`
  - `frontend/src/pages/Overview.tsx` (shared contract columns)
  - `frontend/src/ui/primitives.tsx`
  - `frontend/src/lib/api.ts`, `hooks.ts`

## `/contracts/:id` — Contract workspace

- `frontend/src/pages/ContractDetail.tsx`
  - `frontend/src/ui/domain.tsx`
  - `frontend/src/ui/document.tsx`
  - `frontend/src/ui/charts/index.tsx`
  - `frontend/src/ui/primitives.tsx`
  - `frontend/src/pages/shared.tsx`
  - `frontend/src/lib/api.ts`, `hooks.ts`

## `/new` — Intake

- `frontend/src/pages/NewContract.tsx`
  - `frontend/src/ui/primitives.tsx`
  - `frontend/src/lib/api.ts`, `hooks.ts`

## `/inbox` — Legal decisions

- `frontend/src/pages/Inbox.tsx`
  - `frontend/src/pages/shared.tsx`
  - `frontend/src/ui/domain.tsx`
  - `frontend/src/ui/primitives.tsx`

## `/settings` — Policy administration

- `frontend/src/pages/Settings.tsx`
  - `frontend/src/ui/charts/index.tsx`
  - `frontend/src/ui/primitives.tsx`
  - `frontend/src/pages/shared.tsx`
