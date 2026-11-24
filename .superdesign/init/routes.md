# Route map

Router: `frontend/src/main.tsx` using React Router.

| Path | Page | Layout |
|---|---|---|
| `/` | `pages/Overview.tsx` (authenticated) / `pages/Landing.tsx` (public) | `AppShell` / public layout |
| `/contracts` | `pages/Contracts.tsx` | `AppShell` |
| `/contracts/:id` | `pages/ContractDetail.tsx` | `AppShell` |
| `/new` | `pages/NewContract.tsx` | `AppShell` |
| `/inbox` | `pages/Inbox.tsx` | `AppShell` |
| `/ledger` | `pages/Ledger.tsx` | `AppShell` |
| `/analytics` | `pages/Analytics.tsx` | `AppShell` |
| `/settings` | `pages/Settings.tsx` | `AppShell` |
| `/themes` | `pages/Themes.tsx` | `AppShell` |
| `/evaluation`, `/architecture`, `/annotate`, `/ui` | research and support pages | `AppShell` |
| `/signup`, `/verify`, `/forgot`, `/reset` | `pages/SignIn.tsx` exports | public layout |

The primary redesign targets are Overview, Contracts, Contract Detail, New Contract, Inbox, Ledger, and Settings.
