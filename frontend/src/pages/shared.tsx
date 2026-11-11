/* Page-level compositions shared across screens (built from @ui only). */
import { useState } from "react";
import { Check, X } from "lucide-react";
import { Alert, Avatar, Button, Dialog, Field, Input, Row, Stack, useToast } from "@ui";
import { api, ApiError, ContractState, Escalation, titleCase } from "@lib/api";
import { useAuth } from "@lib/auth";

const APPROVE_MEANS: Record<string, string> = {
  risky_clause: "Approving accepts the flagged clauses as drafted. The agents then start negotiating.",
  redline_rejected: "Approving accepts the clause as the customer drafted it. Negotiation continues.",
  new_legal_terms: "Approving accepts the new terms the customer added. Negotiation continues.",
  no_deal_high_value: "Approving hands this deal to a human negotiator. The agents stop.",
  value_limit: "Approving sends the agreed deal for e-signature.",
};

export function EscalationSummary({ escalation }: { escalation: Escalation }) {
  return (
    <Alert tone="critical" title={`${titleCase(escalation.kind)} · ${titleCase(escalation.stage)}`}>
      <ul style={{ margin: 0, paddingLeft: "1.1em" }}>{escalation.triggers.map((t) => <li key={t}>{t}</li>)}</ul>
    </Alert>
  );
}

export function DecisionPanel({ id, escalation, onDone }: { id: string; escalation: Escalation; onDone: (s: ContractState) => void }) {
  const toast = useToast();
  const { user, can } = useAuth();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);

  async function decide(approve: boolean) {
    setBusy(approve ? "approve" : "reject");
    try {
      const s = await api.decide(id, { approve, note });
      toast(approve ? "Approved. The agents have resumed." : "Rejected. The deal is closed.", approve ? "good" : "info");
      onDone(s);
    } catch (e) {
      toast((e as ApiError).message, "critical");
    } finally {
      setBusy(null);
      setConfirmReject(false);
    }
  }

  if (!can("legal")) {
    return (
      <Alert tone="info" title="Waiting for Legal">
        {APPROVE_MEANS[escalation.kind]} Only someone with the Legal or Admin role can decide. They see this in their escalation inbox.
      </Alert>
    );
  }
  return (
    <Stack gap={12}>
      <p className="nx-secondary" style={{ fontSize: "var(--text-sm)" }}>{APPROVE_MEANS[escalation.kind]}</p>
      <Field label="Note for the audit log" htmlFor={`note-${id}`} hint={<Row gap={6}><Avatar name={user.name} /><span>Signed as {user.name} ({user.email})</span></Row>}>
        <Input id={`note-${id}`} value={note} placeholder="Why you decided this" onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Row gap={8} justify="end">
        <Button variant="secondary" icon={<X size={16} />} loading={busy === "reject"} onClick={() => setConfirmReject(true)}>Reject deal</Button>
        <Button variant="success" icon={<Check size={16} />} loading={busy === "approve"} onClick={() => decide(true)}>Approve</Button>
      </Row>
      <Dialog open={confirmReject} onClose={() => setConfirmReject(false)} title="Reject and close this deal?"
        footer={<>
          <Button variant="ghost" onClick={() => setConfirmReject(false)}>Keep it open</Button>
          <Button variant="danger" loading={busy === "reject"} onClick={() => decide(false)}>Reject deal</Button>
        </>}>
        The agents stop negotiating and the contract is closed. The decision and your note are written to the audit ledger.
      </Dialog>
    </Stack>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return <Alert tone="critical" title="Couldn't load this" actions={onRetry && <Button size="sm" onClick={onRetry}>Try again</Button>}>{error.message}</Alert>;
}
