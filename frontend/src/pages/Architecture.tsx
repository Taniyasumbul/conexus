import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { Card, PageHeader, Segmented, Stack } from "@ui";

const DIAGRAMS = {
  system: `flowchart TB
  subgraph IN["INPUTS"]
    DOC["Contract PDF / DOCX / TXT"]
    CRM[("CRM deal history")]
  end
  subgraph SYS["CoNexus multi-agent system"]
    AN["Contract Analyst"]
    RISK["Legal/Risk Agent"]
    MEM["Memory Agent"]
    PRICE["Sales/Pricing Agent"]
    COMM["Communication Agent"]
    subgraph ORCH["Orchestrator - escalation policy"]
      G1{"Deal-breaker clause?"}
      LOOP["Negotiation round"]
      G2{"Redline rejected or new legal terms?"}
      G3{"Agreed?"}
      G6{"Above autonomy limit?"}
    end
  end
  CP["Counterparty"]
  H["Human reviewer"]
  SIGN["E-signature"]
  AUD[("Audit Agent - hash chain")]
  DOC --> AN --> RISK --> G1
  CRM --> MEM --> PRICE
  G1 -- yes --> H
  G1 -- no --> PRICE --> LOOP --> COMM <--> CP
  COMM --> G2
  G2 -- yes --> H
  G2 -- no --> G3
  G3 -- no --> LOOP
  G3 -- yes --> G6
  G6 -- yes --> H
  G6 -- no --> SIGN
  H -- approve --> LOOP
  SIGN -- write back --> CRM
  AN & RISK & PRICE & COMM & H & SIGN -.-> AUD`,
  requests: `sequenceDiagram
  autonumber
  actor U as Sales user
  participant UI as Web app
  participant API as FastAPI
  participant O as Orchestrator
  participant AG as Agents
  actor CP as Counterparty
  actor H as Reviewer
  participant L as Audit ledger
  U->>UI: Upload contract
  UI->>API: POST /api/contracts
  API->>O: analyze()
  O->>AG: Analyst + Risk
  O->>L: EXTRACT_CLAUSES, FLAG_CLAUSE
  U->>UI: Start negotiation
  UI->>API: POST /negotiate
  API->>O: start()
  alt deal-breaker clause
    O->>H: escalation packet
  else safe
    O->>AG: Memory + Pricing + Comms
    O->>CP: offer e-mail
  end
  loop each reply
    CP->>API: POST /reply
    API->>O: on_reply()
    O->>L: RECEIVE_REPLY, SEND_OFFER or ESCALATE
  end
  H->>UI: Approve / reject
  UI->>API: POST /decision
  API->>O: resolve()
  O->>L: APPROVE or REJECT, EXECUTE`,
  states: `stateDiagram-v2
  [*] --> analyzed: POST /contracts
  analyzed --> awaiting_human: deal-breaker clause
  analyzed --> awaiting_reply: offer sent
  awaiting_reply --> awaiting_reply: counter-offer
  awaiting_reply --> awaiting_human: escalation trigger
  awaiting_reply --> signed: agreed within limit
  awaiting_reply --> closed: no deal
  awaiting_human --> awaiting_reply: approve, continue
  awaiting_human --> signed: approve, value limit
  awaiting_human --> closed: reject
  signed --> [*]
  closed --> [*]`,
};
type Key = keyof typeof DIAGRAMS;

export default function Architecture() {
  const [which, setWhich] = useState<Key>("system");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", fontFamily: "Inter, sans-serif", securityLevel: "strict" });
    let alive = true;
    mermaid.render(`m-${which}-${Date.now()}`, DIAGRAMS[which]).then(({ svg }) => { if (alive && ref.current) ref.current.innerHTML = svg; });
    return () => { alive = false; };
  }, [which]);
  return (
    <Stack gap={20}>
      <PageHeader title="Architecture" description="Six agents, one shared state, one escalation policy." />
      <Segmented<Key> label="Diagram" value={which} onChange={setWhich} options={[
        { value: "system", label: "System" }, { value: "requests", label: "Request flow" }, { value: "states", label: "State machine" },
      ]} />
      <Card><div ref={ref} style={{ overflowX: "auto", display: "flex", justifyContent: "center" }} aria-label={`${which} diagram`} /></Card>
    </Stack>
  );
}
