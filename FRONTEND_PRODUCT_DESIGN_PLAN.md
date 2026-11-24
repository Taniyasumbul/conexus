# CoNexus frontend product-design improvement plan

**Scope:** frontend design, information architecture, component consistency, accessibility, and implementation order. No frontend code is changed by this plan.

**Goal:** make CoNexus feel like a deliberate, trustworthy contract-operations product—calm, fast, and clear for Sales, Legal, and Admin users—not like a generic AI dashboard.

---

## 1. Product-design decision

CoNexus should present itself as a **contract operations workspace**, with AI as a transparent assistant inside the workflow—not as the visual identity of the product.

This approach fits the product category. Modern contract-management tools emphasize a single place to find work, clear workflow status, activity history, review, approvals, signing, and archive rather than presenting AI effects as the main interface. [Ironclad’s workflow and dashboard guidance](https://support.ironcladapp.com/hc/en-us/articles/30794550432151-Ironclad-s-New-Dashboard-and-Workflow-Page-Overview-April-2025-Release) and [Juro’s negotiation flow](https://intercom.help/juro/en/articles/5897857-negotiating-in-juro) support this model.

### Design principles

1. **Work first, AI second.** Put the next human action, current owner, agreement stage, and risk in front of “agent” visuals.
2. **One stable system.** Use one product palette, one spacing scale, one content width, one table pattern, and one action hierarchy.
3. **Evidence before automation.** Every AI suggestion must show source clause, reason, confidence/uncertainty, and the available human action.
4. **Calm density.** Contract work is information-rich. Prefer quiet surfaces, strong type hierarchy, and progressive disclosure over empty cards, decorative gradients, and oversized metrics.
5. **Status is language, not color.** Every state uses a named badge, icon, and accessible color treatment.
6. **No dead ends.** Loading, empty, error, and permission states must say what happened and provide the next useful action. This follows [Carbon’s empty-state guidance](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states).

---

## 2. Findings from the current frontend

### What is already strong

- A real shared UI library exists in `frontend/src/ui/`, with a clear public API via `@ui`.
- The product already has valuable domain-specific components: status badges, risk displays, redline diff, negotiation thread, price chart, audit timeline, deal stepper, and decision panel.
- Core pages have clear route boundaries: overview, contracts, contract detail, inbox, ledger, analytics, intake, and settings.
- Loading, error, empty, mobile-navigation, dark-mode, and keyboard-row behavior already exist in several areas.

### What makes it feel less polished today

| Area | Current signal | Improvement direction |
|---|---|---|
| Product identity | Gradients, animated counters/agent visualization, many selectable palettes, and research items share attention with work | Make the product feel like a legal-operations tool: restrained surfaces, one default palette, quieter motion, and task-first navigation. |
| Information architecture | Work, research/demo, UI gallery, and architecture all appear near core actions | Separate everyday work from research/demo/admin destinations. |
| Overview | Hero is visually strong but gives equal attention to decorative agent activity and operational work | Replace with an action-led “My work” dashboard and a compact portfolio summary. |
| Contract detail | It contains the right information but competes across many cards, tabs, and a large right rail | Turn it into a focused review workspace with a persistent state/action bar and a document-first layout. |
| Data work | Repository has search and status filters, but no saved views, visible sort, batch actions, or responsive card alternative | Standardize a powerful contract table pattern. |
| Naming | UI uses “Signed” while the backend currently sends an e-sign envelope/stub | Use precise lifecycle language such as “Ready for signature” or “Signature requested” until verified completion exists. |
| Theme system | Tokens include many product palettes, while UI documentation describes fonts differently from the source | Keep one production brand theme, make optional personalization secondary, and correct design-system documentation. |
| Quality control | No frontend test/lint/format scripts are defined beyond TypeScript build/typecheck | Add visual, accessibility, and interaction checks before redesign rollout. |

---

## 3. Target information architecture

Keep core work paths immediately visible. Move learning/demo/research material out of the primary daily navigation.

```text
CoNexus
├── Home / My work
├── Contracts
│   ├── All contracts
│   ├── Needs my attention
│   ├── Negotiating
│   └── Completed
├── Review queue                (Legal/Admin only)
├── Reports
│   ├── Portfolio
│   └── Audit history
├── Create contract             (persistent primary action)
└── Admin / Learn               (secondary menu)
    ├── Policy settings
    ├── Team
    ├── Evaluation
    ├── Annotation
    ├── Architecture
    └── Component library
```

### Rules

- “Review queue” replaces the vague primary label “Inbox” for Legal/Admin users. Sales users see “Waiting on Legal” rather than a queue they cannot act on.
- “Ledger” belongs under Reports or Admin unless audit verification is a primary daily workflow for the user’s role.
- Architecture, evaluation, annotation, themes, and component library remain available, but must not compete with contracts, approvals, or create actions.
- Keep one obvious primary action: **Create contract**. Do not create several equivalent “new/upload/analyze” entry points.

---

## 4. Visual system: professional, not AI-generic

### 4.1 Establish one production visual direction

Adopt a **quiet legal-operations workspace**:

- Default: neutral blue-gray page background, white content surfaces, dark navy ink, and one restrained ocean/teal action color.
- Use a single brand accent for action and focus; reserve green/amber/red for success, review, warning, and risk states.
- Prefer 1px borders and subtle elevation. Use large shadows only for dialogs and transient overlays.
- Use gradients only on the public landing page or a single small brand flourish—not on operational screens.
- Use `Plus Jakarta Sans` for headings, `Inter` for reading, and `JetBrains Mono` only for contract IDs, hashes, money calculations, and technical audit data.
- Remove or demote palette switching from the primary account menu. A serious B2B workspace should not change brand color per user by default.

### 4.2 Define component contracts

Before redesigning pages, formalize these component rules in the library:

| Component | Standard behavior |
|---|---|
| Page header | Title, one-sentence purpose, optional compact meta, and max two actions. |
| Button hierarchy | One primary action per area; secondary for reversible alternatives; ghost for tertiary/navigation; danger only in confirmation contexts. |
| Card | Use only when grouping a related task or information set. Avoid a card around every sentence or metric. |
| Table | Sticky header where appropriate; sort state, row hover/focus, filters, overflow actions, pagination, selected-row batch bar, responsive card fallback. |
| Status badge | Fixed lifecycle vocabulary, icon plus text, same meaning everywhere. |
| Risk badge | Separates severity from review state; never rely on red alone. |
| Empty/error/loading | Purpose-specific copy and next action; skeletons for expected loading, not spinners. |
| Forms | Labels, help text, inline validation, disabled/busy behavior, review step for irreversible submission. |
| Side panel | Use for contextual inspection, filters, or lightweight review; use full page for document review. |

### 4.3 Accessibility baseline

1. Meet WCAG 2.2 AA contrast for text and interaction states.
2. Keep visible keyboard focus, semantic buttons/links, logical headings, native form labels, dialog focus trapping, and screen-reader announcements for state changes.
3. Do not communicate risk, success, or selection with color alone; pair with text and icons.
4. Honor `prefers-reduced-motion`; remove nonessential count-up/ambient animation from core work pages.
5. Verify all workflows at 320px, 768px, 1024px, and wide desktop.

Google’s accessibility guidance recommends high contrast, broad user testing, and avoiding color-only meaning; its cited baseline is 4.5:1 for normal text. [Google Design accessibility guidance](https://design.google/library/designing-global-accessibility-part-iii).

---

## 5. Priority implementation sequence

Implement in this order. Do not begin broad page restyling before the design-system and workflow decisions are settled.

### Phase 0 — Design foundation and measurement

**Purpose:** create a shared visual language and a way to detect regressions.

1. Audit all current components and eliminate duplicated page-level button, spacing, badge, table, and loading styles.
2. Reduce `tokens.css` to a documented production palette and semantic token groups: surface, text, border, action, status, focus, data visualization.
3. Correct UI-library documentation to match actual font usage and navigation structure.
4. Add a Storybook-equivalent gallery path or improve the existing `/ui` gallery with every state: default, hover, focus, disabled, busy, error, empty, and dark mode.
5. Add ESLint, Prettier, component tests, and automated accessibility checks.
6. Capture baseline screenshots of the seven primary pages at desktop/tablet/mobile widths.

**Files likely affected later:** `frontend/src/ui/tokens.css`, `styles.css`, `primitives.tsx`, `domain.tsx`, `pages/Gallery.tsx`, `docs/UI_LIBRARY.md`, `frontend/package.json`.

**Acceptance criteria:** every UI pattern has one reusable source; no page needs a new literal color or arbitrary spacing value to match the system.

### Phase 1 — Navigation and product shell

**Purpose:** make it obvious where users should go and what they should do next.

1. Redesign `AppShell` around the target information architecture.
2. Create role-aware navigation labels: Sales sees portfolio/action status; Legal sees review workload; Admin sees governance tools.
3. Move Research/Architecture/Component gallery into a secondary “Learn” or “Developer” menu.
4. Make the global create action persistent and consistent on desktop and mobile.
5. Add a contextual breadcrumb/back affordance on contract detail and settings subviews.
6. Make mobile navigation a true task menu—not a direct copy of every desktop destination.

**Acceptance criteria:** a first-time Sales user can create a contract and find a negotiating contract; a Legal user can find their review queue within one navigation choice.

### Phase 2 — Redesign the core user journey

**Purpose:** make the most valuable sequence feel coherent.

#### A. Create contract (`/new`)

1. Build a concise guided intake: source → business context → review & analyze.
2. Clearly explain accepted formats, privacy handling, expected analysis time, and what happens next.
3. Preserve a “Use a sample contract” option, but visually label it as demo/training content.
4. Validate inline; show a review summary before submit; preserve entered values after error.
5. After analysis, take the user to a clear results/review state, not a generic detail page without orientation.

#### B. My work / overview (`/`)

1. Replace the decorative hero-first experience with an action-led dashboard.
2. First section: **Needs attention** (Legal decisions, failed sends, stalled negotiations, missing information).
3. Second: **My active contracts**, a compact, sortable table/list with stage, owner, counterparty, value, risk, and next action.
4. Third: portfolio snapshot (only 3–4 useful measures, not a wall of KPI cards).
5. Move agent activity to a compact “Activity” rail or collapsible module. It should support trust, not dominate the page.

#### C. Contracts repository (`/contracts`)

1. Add view tabs: All, Mine, Needs review, Negotiating, Awaiting signature, Completed.
2. Add filter chips/drawer: stage, risk, owner, segment, date, value range.
3. Add visible sort control, result count, saved views, and clear-filter action.
4. Add row overflow actions and batch actions where the backend supports them; avoid faux controls.
5. Preserve table behavior on desktop; switch to compact contract cards on small screens.

**Acceptance criteria:** the end-to-end journey “create → analyze → start → resolve review → audit” can be completed without the user needing to interpret an agent visualization.

### Phase 3 — Make contract detail the flagship workspace

**Purpose:** turn the most complex screen into a confident contract-review experience.

### Recommended desktop layout

```text
Breadcrumbs / Contract ID                        [Download redline] [More]
Customer + status + owner + next action
Lifecycle stepper / stage explanation

┌────────────────────────────────────────────────┬───────────────────────────┐
│ Document / negotiation workspace                │ Context rail              │
│ [Document] [Negotiation] [Review] [Activity]    │ Next action               │
│                                                  │ Key terms                 │
│ Readable contract text with anchored risk pins  │ Risk summary              │
│ and redline review                              │ Stakeholders / reviewer   │
│                                                  │ Latest activity           │
└────────────────────────────────────────────────┴───────────────────────────┘
```

### Detail-page rules

1. Add a persistent **next action** panel at the top: “Start negotiation,” “Legal review required,” “Waiting for counterparty,” “Ready for signature,” or “Closed.”
2. Make Document review the default tab after analysis; use negotiation as default only while negotiating.
3. Use the document as the evidence surface: clicking a risk opens/highlights the exact clause and suggested redline.
4. Convert the current large set of peer tabs into four task labels: Document, Negotiation, Review, Activity. Put audit events under Activity.
5. Keep pricing/memory as a collapsible evidence module or an analyst panel rather than a top-level task for every user.
6. Show a compact, chronological activity log with clear actor labels: CoNexus, Legal, Sales, Counterparty, System.
7. Place destructive/rejection decisions in confirmation dialogs and show the consequence before committing.
8. Use exact signing language that matches the backend’s real state.

**Acceptance criteria:** a reviewer can answer within 30 seconds: What is this contract? What is the risk? Who must act? What exactly happens if I approve or reject?

### Phase 4 — Legal review, audit, and administration

**Purpose:** make high-consequence work feel safe and easy to scan.

1. Redesign the review queue as a prioritized worklist rather than a stack of full cards.
2. Sort by urgency and business impact; show counterparty, issue, stage, value, time waiting, owner, and recommended next action.
3. Open review in a side-by-side workspace: decision panel beside the exact clause/redline and activity context.
4. Require/encourage a reason for material legal decisions with a visible audit preview.
5. Redesign the ledger as a filterable event log with contract links, actor filters, dates, event types, verification state, and export/print affordances.
6. Simplify settings into clearly separated Policy, Team, Integrations, and History areas. Explain impacts before changing global thresholds.

**Acceptance criteria:** a Legal user can triage ten reviews efficiently and an Admin can prove why a policy or contract state changed.

### Phase 5 — States, feedback, and content design

**Purpose:** make the app feel thoughtful in non-happy paths.

1. Create a state matrix for every main page: first use, empty, loading, search-empty, permission denied, network error, validation error, saved/success, and long-running background task.
2. Use short, direct, human language. Replace internal technical wording (for example, unexplained “agents” or hashes) with user-oriented labels plus optional details.
3. Add progress feedback for analysis, negotiation start, background changes, document processing, and downloads.
4. Use undo only for safe/reversible actions; use explicit confirmation for contract closure, rejection, and global policy changes.
5. Use skeletons for predictable page/table loading, consistent with [Carbon’s data-table loading guidance](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines).

**Acceptance criteria:** every empty/error state tells the user what changed, why, and the next action if one exists.

---

## 6. Page-by-page implementation backlog

| Order | Screen | Change | Reuse/build |
|---:|---|---|---|
| 1 | App shell | Role-aware work navigation and secondary Learn/Admin menu | `AppShell`, navigation model |
| 2 | New contract | Three-step guided intake and submission confirmation | Stepper, upload field, review summary |
| 3 | Overview | Action-led “My work” dashboard | Work queue, compact portfolio cards, activity module |
| 4 | Contracts | Saved/filterable/sortable repository | Filter bar, data-table toolbar, mobile cards |
| 5 | Contract detail | Document-first review workspace and next-action rail | Workspace layout, activity feed, anchored clause inspector |
| 6 | Review queue | Prioritized legal triage and decision workspace | Queue table, urgency tag, decision drawer/panel |
| 7 | Ledger | Searchable/filterable audit log | Event table, verification banner, event inspector |
| 8 | Settings | Governance-focused settings hierarchy | Impact preview, change review, history table |
| 9 | Analytics | Executive-ready reports with definitions | Date filters, metric definitions, chart/table pairs |
| 10 | Landing/sign-in | Align public/auth experience with product brand | Minimal brand layout, trust copy, accessible forms |

---

## 7. Design constraints to prevent an “AI frontend” look

Use these rules during implementation and review:

- Do not use multi-color gradients, glowing borders, floating blob graphics, pseudo-terminal panels, or animated background effects in operational screens.
- Do not label every action “AI-powered,” “smart,” or “agentic.” Name the job: analyze, flag, propose, review, send, approve, sign.
- Do not show dashboards full of evenly sized cards. Establish one primary task, one secondary workspace, and supporting detail.
- Do not introduce icon-only controls without tooltips and accessible names.
- Do not use more than one primary call to action in a page header or decision surface.
- Do not make users read a wall of text to understand a risk; use a clear conclusion, evidence, and “show more.”
- Do not show mock data as if it were real customer work. Mark sample/demo data visibly and consistently.
- Do not add a new component variant for a one-page need; compose existing primitives first.

---

## 8. Validation plan

### Usability testing

Test with at least 5 representative users across Sales, Legal, and Admin roles. Give each role these tasks:

1. Create and analyze a contract.
2. Find a contract that needs attention.
3. Explain its current stage and next action.
4. Review a risky clause and make/decline a decision.
5. Find why a contract changed state.
6. Change a policy safely (Admin only).

Measure task success, time, misclicks, confidence, and unprompted comprehension of status/risk labels. Test keyboard-only and screen-reader-critical flows. Accessibility research should include target users and different ability levels, not just automated scans. [Google Design’s accessibility research guide](https://design.google/library/designers-guide-accessibility-research).

### Engineering checks

1. Typecheck and production build on every pull request.
2. Add component/unit tests for controls and state variants.
3. Add end-to-end tests for create, start, escalation, decision, and detail-page navigation.
4. Run automated accessibility tests for critical routes.
5. Run visual regression screenshots across light/dark, desktop, tablet, and mobile.
6. Review all new UI against the component gallery and the constraints in section 7.

---

## 9. Definition of done

The redesign is complete when:

- Every core workflow uses the same shell, action hierarchy, terminology, spacing, status system, and feedback patterns.
- Users can find their next task without decoding an AI visualization or visiting a research page.
- Contract detail clearly presents the document, risk evidence, current owner, and next action.
- Tables, filters, empty states, loading states, errors, and mobile layouts are consistent across the product.
- The UI meets accessibility and keyboard requirements, with color never as the only status signal.
- Demo/research content is clearly separated from operational content.
- The design is validated with users and protected by visual/accessibility regression checks.

---

## 10. Recommended first sprint

1. Freeze one production palette and update the design-token documentation.
2. Simplify `AppShell` navigation and separate Work from Learn/Admin.
3. Build the common table toolbar, filter bar, status vocabulary, and state components.
4. Redesign New Contract, Contracts, and Contract Detail as one continuous workflow.
5. Validate these three pages with Sales and Legal users before touching analytics, research, or theme personalization.

This sequence gives the product the largest visible improvement while preserving the existing domain-specific UI work that already differentiates CoNexus.
