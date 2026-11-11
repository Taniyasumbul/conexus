# Clause Annotation Guidelines (RO2 ground truth)

Perspective: a **small software vendor with no in-house legal team** reviewing a
**customer-drafted** contract. Annotators label each clause with three fields.

## 1. `level` - commercial / legal risk to the vendor

| Level | Meaning | Examples |
|---|---|---|
| low | Market-standard, balanced | net 30 payment; mutual liability cap of 12 months' fees; mutual confidentiality for 3 years |
| medium | Off-market but bounded; costs money, not survival | net 45-60; foreign governing law; one-sided assignment; price lock on renewal |
| high | Materially off-market or unbounded | net 90+; termination for convenience with full refund; 100% uptime guarantee; uncapped liability |

## 2. `requires_human` - must a human decide before signing?

Mark **true** only if the clause creates exposure the vendor **cannot price or reverse**:

1. Uncapped vendor liability, or a cap far above market (> 2x annual fees), or a one-sided exclusion of consequential damages.
2. Indemnity covering the customer's own negligence, or "any and all claims" regardless of fault.
3. Transfer of the vendor's background IP, platform, tools or improvements to the customer.
4. Exclusivity or non-compete obligations binding the vendor.
5. Strict liability for data breaches or regulatory fines, or unlimited and unannounced audit rights.

Everything else is **false**, even if it is high risk commercially. Those are handled by autonomous redlines.

## 3. `redlinable` - is there a standard fallback the agent may propose on its own?

True when the playbook has a standard fallback position (see `REDLINES` in
`conexus/agents/risk.py`), e.g. payment terms -> net 30, liability -> 12 months' fees.
A clause can be both `requires_human` and `redlinable` (e.g. uncapped liability):
the agent proposes the fallback, and **escalates if the counterparty rejects it**.

## 4. Contract-level label

`should_escalate = any(clause.requires_human)`.

## 5. Process for the paper

- Two annotators label independently; report Cohen's kappa on `requires_human`.
- Disagreements are resolved by the supervisor / a practising lawyer.
- Source contracts: CUAD (510 real commercial contracts, CC BY 4.0) mapped to the
  clause types in `conexus/models.py::ClauseType`, plus any real SME contracts the
  team can obtain with permission (anonymised).
- Keep a held-out test set that nobody looks at while tuning rules or thresholds.

## 6. Using the Annotate page

1. Open `/annotate` (or a personal link: `/annotate?annotator=<name>`).
2. Read the clause from the vendor's side and press `H` (needs a human), `S` (agent may handle) or
   `U` (unsure). For H/S also set the level (`1`-`3`) and whether a standard fallback exists (`R`).
3. Press `Enter` to save. Only then does the page show the CUAD category, the proxy label and the
   model's opinion, so they cannot anchor your judgement.
4. The second annotator automatically gets clauses the first one already labelled, so Cohen's kappa
   appears in the sidebar. Aim for 150+ overlapping clauses and kappa >= 0.6 before adjudicating.
5. Labels export to `data/labels/expert_cuad.jsonl`; `make eval` scores the system against them.
