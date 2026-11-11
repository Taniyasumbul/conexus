# CoNexus Architecture

## 1. System overview

```mermaid
flowchart TB
    subgraph IN["INPUTS"]
        DOC["Contract<br/>PDF / DOCX / TXT"]
        CRM[("CRM deal history")]
    end

    subgraph SYS["CoNexus Multi-Agent System"]
        direction TB
        AN["1 - Contract Analyst Agent<br/>split clauses, read opening price"]
        RISK["2 - Legal/Risk Agent<br/>rules + ML + LLM risk score"]
        MEM["3 - Memory Agent<br/>find similar past deals"]
        PRICE["4 - Sales/Pricing Agent<br/>anchor, floor, concessions"]
        COMM["5 - Communication Agent<br/>write and parse emails"]
        STATE[("Shared Negotiation State<br/>persisted in SQLite")]

        subgraph ORCH["Negotiation Orchestrator - escalation policy"]
            G1{"Clause needs a human<br/>and has no safe redline?"}
            RL["Propose redlines for<br/>off-market clauses"]
            LOOP["Negotiation round N"]
            G2{"Risk-critical redline rejected<br/>or new legal terms added?"}
            G3{"Deal agreed?"}
            G4{"Rounds left?"}
            G5{"High-value deal?"}
            G6{"Value above<br/>autonomy limit?"}
        end
    end

    subgraph OUT["OUTPUTS"]
        CP["Counterparty<br/>email / Slack"]
        HUMAN["Human reviewer<br/>escalation inbox"]
        SIGN["E-signature<br/>DocuSign"]
        NODEAL["No agreement"]
    end

    AUD[("6 - Audit Agent<br/>hash-chained, tamper-evident log")]

    DOC --> AN --> RISK --> G1
    CRM --> MEM --> PRICE
    AN & RISK & PRICE & COMM <--> STATE

    G1 -- "Yes" --> E1["ESCALATE<br/>pre-negotiation"]
    G1 -- "No" --> RL --> PRICE --> LOOP
    LOOP --> COMM <--> CP
    COMM --> G2
    G2 -- "Yes" --> E2["ESCALATE<br/>in-negotiation"]
    G2 -- "No" --> G3
    G3 -- "No" --> G4
    G4 -- "Yes" --> LOOP
    G4 -- "No" --> G5
    G5 -- "Yes" --> E2
    G5 -- "No" --> NODEAL
    G3 -- "Yes" --> G6
    G6 -- "Yes" --> E3["ESCALATE<br/>pre-signature"]
    G6 -- "No" --> SIGN

    E1 & E2 & E3 --> HUMAN
    HUMAN -- "approve" --> LOOP
    SIGN -- "write back" --> CRM

    AN -.-> AUD
    RISK -.-> AUD
    PRICE -.-> AUD
    COMM -.-> AUD
    E1 & E2 & E3 -.-> AUD
    HUMAN -.-> AUD
    SIGN -.-> AUD
    NODEAL -.-> AUD

    classDef agent fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef gate fill:#fff8e1,stroke:#f9a825,color:#5d4037
    classDef esc fill:#ffebee,stroke:#c62828,color:#b71c1c
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef store fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    class AN,RISK,MEM,PRICE,COMM agent
    class G1,G2,G3,G4,G5,G6 gate
    class E1,E2,E3,HUMAN esc
    class SIGN good
    class CRM,STATE,AUD store
```

## 2. Deployment view

```mermaid
flowchart LR
    U["Sales user / Legal reviewer"] --> UI["React web app<br/>Nexus UI"]
    UI -- "REST / JSON" --> API["FastAPI<br/>:8000"]
    MAIL["Mail provider<br/>inbound parse"] -- "POST /reply" --> API
    API --> ORCH["Orchestrator<br/>state machine"]
    ORCH --> AGENTS["6 agents"]
    AGENTS --> LLM["LLM provider<br/>Claude / Ollama / offline"]
    API --> DB[("SQLite<br/>contracts + state")]
    ORCH --> LOG[("audit.jsonl<br/>hash chain")]
    ORCH --> SLACK["Slack webhook<br/>escalations"]
    ORCH --> SMTP["SMTP<br/>offers"]
    ORCH --> DS["DocuSign<br/>(stub)"]
    ORCH --> CRMS[("CRM<br/>CSV / HubSpot")]
```

## 3. Request flow

```mermaid
sequenceDiagram
    autonumber
    actor U as Sales User
    participant UI as Dashboard
    participant API as FastAPI
    participant DB as SQLite
    participant O as Orchestrator
    participant AG as Agents (Analyst, Risk, Memory, Pricing, Comms)
    participant LLM as LLM
    actor CP as Counterparty
    actor H as Reviewer
    participant DS as DocuSign
    participant AUD as Audit Log

    U->>UI: upload contract + deal details
    UI->>API: POST /api/contracts (multipart)
    API->>O: analyze(text, context)
    O->>AG: Analyst.analyze, Risk.assess_all
    opt LLM mode
        AG->>LLM: classify / assess clause (JSON schema)
    end
    O->>AUD: EXTRACT_CLAUSES, FLAG_CLAUSE
    API->>DB: INSERT state (status=analyzed)
    API-->>UI: 201 clauses + risks

    U->>UI: start negotiation
    UI->>API: POST /api/contracts/{id}/negotiate
    API->>O: start(state)
    alt deal-breaker clause
        O->>AUD: ESCALATE (risky_clause)
        O->>H: Slack packet
        API->>DB: status=awaiting_human
    else safe
        O->>AG: Memory.retrieve -> Pricing.plan -> Comms.compose
        O->>CP: offer e-mail (round 1)
        O->>AUD: PRICING_PLAN, SEND_OFFER
        API->>DB: status=awaiting_reply
    end
    API-->>UI: 200 state

    loop until agreed / escalated / failed
        CP->>API: POST /api/contracts/{id}/reply (webhook)
        API->>DB: load state
        API->>O: on_reply(state, message)
        O->>AG: Comms.parse, check redlines & new terms, Pricing.next_offer
        O->>AUD: RECEIVE_REPLY, SEND_OFFER / ESCALATE / ACCEPT
        API->>DB: save state
    end

    H->>UI: open escalation inbox
    UI->>API: GET /api/escalations
    H->>UI: approve / reject
    UI->>API: POST /api/contracts/{id}/decision
    API->>O: resolve(state, decision)
    O->>AUD: APPROVE / REJECT (human:reviewer)
    alt approved and agreed
        O->>DS: create envelope (terms + audit head hash)
        O->>AUD: EXECUTE, WRITE_BACK
    else approved mid-negotiation
        O->>CP: next offer (machine resumes)
    end
    API->>DB: save state

    H->>API: GET /api/audit/verify
    API->>AUD: recompute hash chain
    API-->>H: chain intact
```

## 4. Orchestrator state machine

```mermaid
stateDiagram-v2
    [*] --> analyzed: POST /contracts
    analyzed --> awaiting_human: start() - deal-breaker clause
    analyzed --> awaiting_reply: start() - offer sent
    awaiting_reply --> awaiting_reply: on_reply() - counter-offer
    awaiting_reply --> awaiting_human: redline rejected / new legal terms / failed high-value / above limit
    awaiting_reply --> signed: agreed within autonomy limit
    awaiting_reply --> closed: walked away / no agreement
    awaiting_human --> awaiting_reply: approve (continue)
    awaiting_human --> signed: approve (value_limit)
    awaiting_human --> closed: reject / handed off
    signed --> [*]
    closed --> [*]
```

## 5. API reference

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/contracts` | Upload (`file`) or pick `sample_id` + deal context, runs Analyst + Risk |
| GET | `/api/contracts` | List contracts with status |
| GET | `/api/contracts/{id}` | Full negotiation state |
| POST | `/api/contracts/{id}/negotiate` | Start: `{"mode": "simulated"\|"email", persona, wtp, delay_s}` |
| POST | `/api/contracts/{id}/reply` | Inbound counterparty reply (e-mail webhook) |
| POST | `/api/contracts/{id}/decision` | Human decision `{"approve": bool, "reviewer", "note"}` |
| GET | `/api/escalations` | Human review inbox |
| GET | `/api/contracts/{id}/audit` | Decision trail for one contract |
| GET | `/api/audit/verify` | Verify the global hash chain |
| GET | `/api/metrics` | Portfolio KPIs |
| GET | `/api/samples` | Bundled demo contracts and scenarios |
| GET | `/api/eval` | Latest evaluation results |
| GET | `/health` | Liveness + active LLM provider |

Interactive OpenAPI docs: `http://localhost:8000/docs`.

## 6. Escalation kinds

| Kind | Stage | Trigger | Human "approve" means |
|---|---|---|---|
| `risky_clause` | pre-negotiation | clause needs a human and has no autonomous fallback | flagged clauses accepted, negotiation starts |
| `redline_rejected` | in-negotiation | counterparty rejects redline on a risk-critical clause | clause accepted as drafted, negotiation continues |
| `new_legal_terms` | in-negotiation | counterparty introduces new legal obligations | new terms accepted, negotiation continues |
| `no_deal_high_value` | in-negotiation | talks fail on a deal above the high-value threshold | a human takes the deal over |
| `value_limit` | pre-signature | agreed value above the autonomy limit | deal is signed |

"Reject" always closes the deal. All thresholds live in `conexus/config.py` (`EscalationPolicyConfig`).
