# Shared layouts

## `frontend/src/ui/AppShell.tsx`

The authenticated application shell. It renders a sticky top bar with the CoNexus logo, primary navigation, research menu, global create action, notification bell, theme control, account menu, mobile sheet, optional demo banner, and a constrained main-page container.

Navigation groups:

- Work: Overview, Contracts, Inbox, Ledger, Analytics.
- Secondary/research: Evaluation, Clause annotation, Architecture, Component library.
- Settings is available from primary navigation and account menu.

The redesign should keep one stable shell across all signed-in product pages, but simplify navigation emphasis so operational work is distinct from demo/research material.

## `frontend/src/main.tsx`

The application root supplies BrowserRouter, authentication gate, toast provider, lazy page loading, shell placement, notification polling, and the route map.

## `frontend/src/pages/Landing.tsx` and `frontend/src/pages/SignIn.tsx`

Public marketing and authentication surfaces. They should share brand, typography, spacing, and form behavior with the authenticated shell without copying its dense navigation.
