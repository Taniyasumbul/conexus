git# CoNexus backend improvement plan

**Scope:** backend only. This document is an implementation roadmap; it does not change application code.

**Assessment date:** 21 November 2026  
**Evidence reviewed:** `project_inside.md`, backend source under `conexus/`, backend tests, configuration, deployment files, and declared Python dependencies.

---

## 1. Executive decision

### LangGraph status: not in use

CoNexus does **not** use LangGraph or LangChain.

- `pyproject.toml` declares neither package.
- A repository-wide search found no `langgraph`, `StateGraph`, or LangChain workflow usage.
- Workflow control is implemented directly by `conexus/orchestrator.py` in the `Orchestrator` class.
- The shared state object is the Pydantic `NegotiationState` model, and `Store` persists it as JSON.

This is not inherently a problem. The current workflow is a small, understandable, deterministic state machine with explicit human-review gates. Replacing it with LangGraph now would add framework migration risk without resolving the most important defects below.

**Recommendation:** retain the custom orchestrator through phases 0–3. Re-evaluate LangGraph only after the core correctness, persistence, and job-execution work is complete, and only if the product needs durable distributed workflow execution, resumable node-level runs, visual graph operations, branching workflows, or many independently deployable agents.

---

## 2. Current backend strengths to preserve

- A clearly bounded workflow: `analyzed → awaiting_reply | awaiting_human → signed | closed`.
- Typed domain models and validation via Pydantic.
- A centralized orchestration boundary: lifecycle transitions live in `Orchestrator`, rather than being scattered across API routes.
- Explicit human-in-the-loop escalation kinds and approval outcomes.
- Offline fallback paths for the agents.
- A linked SHA-256 audit chain and behavioral backend tests.
- SQLite for local use with an existing PostgreSQL option.

Improvements should retain these properties. In particular, do not move lifecycle decisions into route handlers or make LLM output authoritative without deterministic validation.

---

## 3. Priority and sequence

Complete each phase in order. A phase is finished only when its acceptance criteria and tests pass.

| Phase | Priority | Outcome | Why it must come here |
|---|---|---|---|
| 0 | P0 | Freeze baseline and add regression coverage | Makes later changes safe and measurable. |
| 1 | P0 | Correct unsafe negotiation decisions | Prevents accidental signing and undeliverable email. |
| 2 | P0 | Protect API and data boundaries | Reduces immediate production security and reliability risk. |
| 3 | P1 | Make state, CRM, audit, and jobs durable | Required before multi-process deployment. |
| 4 | P1 | Improve workflow structure and observability | Makes behavior diagnosable and maintainable. |
| 5 | P2 | Improve AI governance and evaluation | Protects legal/commercial decisions as model use grows. |
| 6 | P2 | Production readiness and engineering hygiene | Reduces operational cost and regression risk. |
| 7 | P3 | Reassess LangGraph or another workflow engine | Do this only from demonstrated workflow needs. |

---

## 4. Phase 0 — establish a safe baseline

### 0.1 Record the supported deployment model

**Current issue:** parts of the application depend on in-process state: locks, CRM memory, and audit-chain state. The present design is therefore effectively single-process.

**Work:**

1. State explicitly in backend deployment documentation that production is single worker until phase 3 is complete.
2. Pin a supported Python version in CI, Docker, and local setup instructions.
3. Document required environment variables, without placing secrets in source control.
4. Create a short architecture decision record (ADR) for the custom state machine and its invariants.

**Acceptance criteria:** an operator can determine the supported worker count, storage requirement, and configuration source without reading application code.

### 0.2 Add regression tests before behavior changes

Add narrowly focused tests for all P0 defects before fixing them.

Required test cases:

- A message such as “We are no longer interested in this deal” closes or escalates the negotiation; it never signs it.
- A true acceptance, such as “We accept your proposal,” signs only the exact pending offer.
- Email mode stores and uses a valid counterparty email address.
- Invalid or oversized uploads are rejected without parsing.
- Repeated webhook messages cannot advance the same negotiation twice.

**Acceptance criteria:** tests fail on the current vulnerable behavior and pass after phase 1.

---

## 5. Phase 1 — fix correctness defects in negotiation and email

### 1.1 Fix acceptance versus walk-away precedence

**Severity:** critical.

`CommunicationAgent` currently recognizes a broad acceptance signal that includes the word `deal`. `Orchestrator.on_reply()` checks `accept` before `walk_away`. A message ending negotiations but containing “deal” can therefore be interpreted as acceptance.

**Work:**

1. Make acceptance detection use explicit, contextual acceptance phrases rather than a bare domain word.
2. Resolve unambiguous termination/rejection before acceptance in orchestration.
3. Treat messages containing conflicting signals as `needs_clarification` or human review, never as automatic signing.
4. Record the parser decision and matched evidence in the audit event, avoiding unnecessary raw-message retention.

**Files expected to change later:** `conexus/agents/communication.py`, `conexus/orchestrator.py`, and backend tests.

**Acceptance criteria:** the false-acceptance regression test is permanently green; ambiguous replies cannot produce `signed` automatically.

### 1.2 Make email mode a complete, validated workflow

**Severity:** critical.

`counterparty_email` is accepted by the request model but is not persisted or read. Outbound mail is addressed to `ctx.customer`, which is a company display name, not an email recipient.

**Work:**

1. Add a validated, normalized recipient field to the contract/domain record.
2. Persist it in a migration and return it only to authorized internal users.
3. Send email to that recipient; keep customer name solely for display and mail salutation.
4. Store provider message IDs and correlation identifiers for outbound and inbound mail.
5. Verify inbound webhook authenticity using provider signature verification where available; retain the existing shared token only as a transitional safeguard.
6. Add idempotency keyed by provider message ID or a message hash.
7. Define explicit delivery states: queued, sent, delivered, bounced, and failed.

**Acceptance criteria:** a configured test SMTP/provider adapter receives a message at the persisted email address, and a duplicate inbound payload does not create another state transition.

### 1.3 Clarify signing semantics

`ESignStub` creates an envelope JSON file, not a legally binding signature transaction.

**Work:**

1. Rename user-facing status from “signed” to “signature requested” until a real provider confirms completion, or integrate an e-sign provider with callbacks.
2. Persist envelope ID, provider status, timestamps, immutable terms, and audit head.
3. Allow the terminal `signed` state only after a verified provider webhook/event.

**Acceptance criteria:** no contract is labeled signed merely because a local JSON envelope was written.

---

## 6. Phase 2 — secure and bound public interfaces

### 2.1 Lock down browser access and sessions

**Current issue:** CORS permits every origin (`allow_origins=["*"]`).

**Work:**

1. Configure an allowlist from environment settings for production origins.
2. Use secure cookies behind HTTPS and verify proxy/forwarded-header configuration.
3. Add CSRF protection for cookie-authenticated state-changing endpoints, or move to an explicitly designed bearer-token approach for the API.
4. Do not enable public/demo Legal capabilities against a database containing real contracts.

**Acceptance criteria:** an unapproved browser origin cannot make authenticated state-changing requests in production configuration.

### 2.2 Add request limits and abuse controls

**Current issue:** uploads are fully read into memory with no size cap; authentication and webhook endpoints have no rate limits.

**Work:**

1. Set a maximum upload size and reject early using `Content-Length` plus a streaming read limit.
2. Set reasonable parser timeouts and file-type validation; consider malware scanning in production.
3. Rate-limit login, sign-up, password-reset, upload, and inbound-webhook endpoints.
4. Add request-body size limits at the reverse proxy as well as the application.
5. Return consistent error envelopes without exposing stack traces or secrets.

**Acceptance criteria:** an oversized upload is rejected predictably; rate-limit tests cover authentication and webhook abuse paths.

### 2.3 Establish authorization scope

**Current issue:** the data model behaves as a single-tenant internal tool: permitted users can access all contracts.

**Work:**

1. Make this single-tenant model explicit if it is intentional.
2. If multiple companies, teams, or deal owners are required, add tenant/workspace and owner columns before any customer deployment.
3. Apply scope checks to every contract, audit, notification, policy, and export query.
4. Add authorization tests for cross-workspace access.

**Acceptance criteria:** the documented isolation model matches the database and API behavior.

---

## 7. Phase 3 — make persistence and execution durable

### 3.1 Replace unsafe simulation serialization

**Current issue:** simulation objects are stored with Python `pickle`. Pickle is unsafe for untrusted data and brittle across code versions.

**Work:**

1. Store only a versioned JSON simulation snapshot (persona, reservation parameters, random seed/state) or recreate it deterministically from stored inputs.
2. Add a schema version and migration/read compatibility policy.
3. Remove deserialization of arbitrary pickle data after existing records have a safe migration path.

**Acceptance criteria:** a simulation survives restart without pickle and produces a deterministic continuation from its stored state.

### 3.2 Persist CRM learning properly

**Current issue:** `CRMStore.record()` appends only to an in-memory list. “Write-back” disappears on restart and is not shared between workers.

**Work:**

1. Define a `deal_records` table or use a genuine CRM adapter as the system of record.
2. Make write-back transactional with final workflow state where practical.
3. Store provenance: source contract, model/policy version, reviewer approvals, and whether the result was simulated or real.
4. Refresh or query memory from durable storage instead of a process-local list.

**Acceptance criteria:** a completed deal remains available to memory after restart and from another worker.

### 3.3 Make audit records durable and verifiable

**Current issue:** audit behavior differs by backend and has process-local chain state; local file storage may be ephemeral in cloud hosting.

**Work:**

1. Make PostgreSQL the production audit source of truth.
2. Persist each event’s sequence, previous hash, hash, contract ID, actor, action, structured payload, schema version, and timestamp.
3. Reconstruct/verify the hash chain from the database on startup.
4. Provide a protected verification endpoint or CLI command and scheduled integrity check.
5. Define retention, export, and access-control rules for audit content.

**Acceptance criteria:** a restart and multi-worker read do not fork the audit chain; deliberate tampering is detected by an automated test.

### 3.4 Replace in-process background execution

**Current issue:** FastAPI `BackgroundTasks`, `threading.Lock`, and `time.sleep()` manage negotiation driving. Locks are per process and a long delay holds the contract lock.

**Work:**

1. Model each delayed action as a durable job with a contract version and idempotency key.
2. Use a job worker/queue appropriate to the deployment (for example PostgreSQL-backed workers first; Redis-backed workers only if needed).
3. Use database row locking or optimistic concurrency versioning around state transitions.
4. Make jobs retryable with bounded retries, dead-letter handling, and observability.
5. Do not hold locks while sleeping or making external calls.

**Acceptance criteria:** duplicate workers cannot process the same transition twice, and a server restart does not lose a pending delayed action.

### 3.5 Introduce versioned database migrations

**Current issue:** schema initialization and a one-off inline migration live in application startup.

**Work:**

1. Adopt a migration tool such as Alembic.
2. Put every schema change in an ordered migration, including the recipient, workflow version, job, CRM, and audit changes above.
3. Run migrations separately from web-process startup in production.
4. Test upgrade from a representative existing SQLite/PostgreSQL database.

**Acceptance criteria:** a fresh install and upgrade both produce the same schema, verified in CI.

---

## 8. Phase 4 — improve backend structure and observability

### 4.1 Separate transport, application, and domain responsibilities

**Current issue:** `conexus/api/server.py` is both composition root and a large set of route handlers with orchestration, persistence, notification, and policy concerns mixed together.

**Work:**

1. Keep FastAPI routes thin: authenticate, validate input, call an application service, serialize output.
2. Extract use cases: create contract, start negotiation, process reply, resolve escalation, send offer, and finalize signature.
3. Define repository interfaces for contracts, audit, CRM, job queue, and outbound channels.
4. Keep `Orchestrator` responsible only for deterministic domain transitions; inject side effects through ports/events.
5. Version state-transition events and use them to drive notifications and integration calls.

**Acceptance criteria:** core negotiation tests can execute with in-memory ports and no FastAPI, SMTP, filesystem, or database dependency.

### 4.2 Formalize state-machine invariants

**Work:**

1. Define allowed transitions in one machine-readable location.
2. Add a monotonically increasing state version for optimistic concurrency.
3. Validate invariants at every transition: terminal states cannot change, approval must match a pending escalation, accepted terms must correspond to a known offer, and signing requires required reviews.
4. Add property/transition tests for invalid event ordering, duplicate delivery, and restart recovery.

**Acceptance criteria:** illegal transitions are rejected with a stable domain error and leave the prior state unchanged.

### 4.3 Add operational telemetry

**Work:**

1. Use structured logs with request ID, contract ID, job ID, actor, event type, and duration.
2. Add health checks that test database connectivity and report dependency readiness without leaking configuration.
3. Export process metrics: request latency/error rate, upload rejection counts, job lag/failures, escalation rate, email delivery failures, and audit-verification failures.
4. Add tracing around LLM, SMTP, database, and job calls.
5. Redact contract text, credentials, and personal data from standard logs and telemetry.

**Acceptance criteria:** an operator can diagnose a failed negotiation or delayed job using an ID without querying raw production records manually.

---

## 9. Phase 5 — strengthen AI and policy governance

### 5.1 Validate model outputs as untrusted input

**Work:**

1. Constrain LLM responses to strict schemas and validate every field.
2. Ground terms, clause IDs, and prices against the contract and pending offer before they affect state.
3. For low-confidence or conflicting extraction, request clarification or escalate; do not infer acceptance.
4. Record model/provider/version, prompt-template version, parser version, and confidence/provenance for decisions.
5. Add prompt-injection tests using contract text and inbound messages that try to alter system behavior.

**Acceptance criteria:** malformed, invented, or injected model output cannot sign a deal, alter policy, or add unsupported legal terms.

### 5.2 Govern risk policy changes

**Current issue:** the policy is global and live changes apply broadly; its history depends on the audit implementation.

**Work:**

1. Version risk and pricing policies immutably.
2. Associate every contract and decision with its policy version.
3. Require an authorized approval workflow for production policy changes.
4. Add a dry-run/simulation endpoint for proposed policy versions.
5. Re-run the evaluation suite before promotion and retain the report with the policy version.

**Acceptance criteria:** a reviewer can reproduce why a contract escalated using the policy version active at that time.

### 5.3 Improve evaluation credibility

**Work:**

1. Separate development, calibration, and held-out test sets for parsers and policies.
2. Replace proxy labels with reviewed legal labels where possible, recording agreement and adjudication.
3. Track false acceptance, false rejection, missed mandatory escalation, and unsafe autonomous-signing rates—not only generic extraction metrics.
4. Set release gates for high-severity regression cases.

**Acceptance criteria:** every policy/parser release has a reproducible evaluation report on data not used to tune it.

---

## 10. Phase 6 — production engineering hygiene

### 6.1 Testing and quality gates

1. Add Ruff formatting/linting and a type checker (Pyright or mypy) for backend code.
2. Run unit, API, PostgreSQL integration, migration, and security regression tests in CI.
3. Add contract tests for SMTP/webhook/e-sign adapters.
4. Test database migrations and restart recovery.
5. Add dependency vulnerability scanning and pin/renovate policy.

### 6.2 Configuration and secrets

1. Validate all settings at startup with environment-specific profiles.
2. Store production secrets in a secret manager, rotate webhook/SMTP credentials, and never log them.
3. Provide `.env.example` with safe placeholders and exact descriptions.
4. Fail closed for missing production security settings rather than silently using development defaults.

### 6.3 Backup and recovery

1. Define PostgreSQL backup frequency, encryption, retention, and restore testing.
2. Include contract source documents and signature artifacts in the retention plan.
3. Test recovery of a contract, audit chain, pending job, and CRM memory in a staging environment.

**Acceptance criteria:** CI blocks unsafe regressions, and the team has a tested restoration procedure.

---

## 11. Phase 7 — optional workflow-engine decision

Do not adopt LangGraph merely because the product has multiple agents. Adopt it only if evidence shows it lowers total complexity.

### Revisit LangGraph if all or most of these become true

- Workflows need many dynamic branches or subgraphs.
- Runs must be interrupted and resumed at arbitrary node boundaries.
- Different teams own independently deployed workflow nodes.
- Operators need graph-level replay, inspection, or human approval tooling.
- Existing custom persistence/job infrastructure is becoming a workflow engine in practice.

### Keep the custom orchestrator if these remain true

- The state machine stays small and deterministic.
- Most transitions are contractual business rules requiring direct tests and simple auditability.
- A single domain team owns the workflow.
- Durable jobs and optimistic concurrency provide the needed recovery/scale characteristics.

### If a migration is approved

1. First finish phase 3 so state and events are durable independently of the engine.
2. Create a compatibility layer that maps current domain events and `NegotiationState` into graph state.
3. Migrate one non-critical path first, keeping existing API contracts unchanged.
4. Run old and new implementations in shadow mode against recorded events.
5. Move sign/escalation paths only after outcome equivalence and audit requirements are proven.

**Decision:** LangGraph is **not a current P0/P1 need**. Correctness, security, durable persistence, and job execution are the prerequisites and provide higher value regardless of the eventual workflow engine.

---

## 12. Suggested delivery milestones

| Milestone | Included phases | Delivery evidence |
|---|---|---|
| Safe prototype | 0–2 | Regression suite, no false acceptance, valid email plumbing, limits/rate controls, documented single-tenant stance. |
| Durable internal service | 3 | PostgreSQL migrations, durable CRM/audit/jobs, restart and duplicate-delivery tests. |
| Operable service | 4 and 6 | Structured logs, metrics, health checks, CI gates, backup/restore exercise. |
| Governed AI service | 5 | Versioned policy/model provenance, held-out evaluation, release gates. |
| Workflow-engine decision | 7 | ADR supported by measured complexity and operational needs. |

---

## 13. First implementation backlog

This is the recommended order for individual pull requests:

1. Add false-acceptance regression tests.
2. Fix parser/orchestrator decision precedence and ambiguity handling.
3. Add tests and persistence for `counterparty_email`; send to recipient rather than customer display name.
4. Add upload size/type guards and their tests.
5. Restrict production CORS and add rate limits to auth/webhook endpoints.
6. Document the single-process/single-tenant deployment constraints.
7. Add versioned migrations and migrate new recipient/state fields.
8. Replace simulation pickle with versioned JSON state.
9. Persist CRM write-back and audit chain in PostgreSQL.
10. Introduce durable, idempotent background jobs with concurrency control.
11. Extract application services and add domain transition/property tests.
12. Add observability, CI quality gates, and backup/recovery verification.

---

## 14. Definition of done for backend production readiness

The backend should not be considered production-ready until it can demonstrate all of the following:

- No ambiguous inbound reply can autonomously sign a contract.
- Email recipient, delivery, inbound correlation, and signature completion are real and tested.
- Browser/API access, uploads, sessions, and webhooks have explicit limits and authorization controls.
- All business-critical state, CRM learning, audit records, and delayed jobs survive restart and multi-worker operation.
- Audit chains are tamper-evident and independently verifiable from durable storage.
- Schema changes are versioned and upgrade-tested.
- A state transition is idempotent, authorized, auditable, and reproducible under its original policy/model version.
- CI exercises PostgreSQL, migrations, security regressions, and integration adapters.
- Monitoring, backups, and recovery procedures are tested—not merely documented.
