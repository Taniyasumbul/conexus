"""Generate the synthetic seed dataset.

Outputs
  data/labels/clauses.jsonl    labelled clauses (RO2 classifier train/test)
  data/contracts/*.txt         full contracts composed from labelled clauses
  data/labels/contracts.jsonl  contract-level ground truth + hidden sim params
  data/crm/deals.csv           historical CRM deals (RO3 memory)

This is a *seed* dataset for development. For the paper, replace / augment the
labels with real contracts annotated by a legal expert (see README).
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from ..agents.analyst import extract_payment_days
from ..config import DATA
from ..sim.world import sample_context, sample_wtp
from .clause_bank import BANK, PREFIXES, SUFFIXES

VENDORS = ["CoNexus Software Pvt Ltd", "BrightStack Technologies", "Vendor"]
CLAUSE_ORDER = [
    "price", "payment_terms", "auto_renewal", "termination", "warranty", "liability_cap",
    "indemnification", "ip_ownership", "confidentiality", "data_protection", "non_compete",
    "assignment", "governing_law", "other",
]


def _fill(text: str, vendor: str, customer: str, price: float = 0, seats: int = 0) -> str:
    return text.format(vendor=vendor, customer=customer, price=f"USD {price:,.0f}", seats=seats)


def gen_clause_labels(rng: random.Random) -> list[dict]:
    rows = []
    for family, ctype, level, human, redl, heading, variants in BANK:
        if ctype == "price":
            continue
        for vi, v in enumerate(variants):
            for k in range(6):
                text = rng.choice(PREFIXES) + _fill(v, rng.choice(VENDORS), rng.choice(["Customer", "the Client", "Buyer"]))
                text += rng.choice(SUFFIXES)
                rows.append({
                    "id": f"{family}-{vi}-{k}", "family": family, "type": ctype, "level": level,
                    "requires_human": human, "redlinable": redl, "text": text.strip(),
                })
    # dedupe identical texts
    seen, out = set(), []
    for r in rows:
        if r["text"] not in seen:
            seen.add(r["text"])
            out.append(r)
    return out


def gen_contracts(rng: random.Random, n: int) -> list[dict]:
    by_type: dict[str, list] = {}
    for entry in BANK:
        by_type.setdefault(entry[1], []).append(entry)

    contracts = []
    contract_dir = DATA / "contracts"
    for old in contract_dir.glob("contract_*.txt"):
        old.unlink()
    for i in range(n):
        ctx = sample_context(rng)
        wtp = sample_wtp(ctx, rng)
        aggressiveness = rng.random()  # how one-sided the customer's paper is
        persona = rng.choices(["cooperative", "hardball", "deadline"], weights=[0.4, 0.4, 0.2])[0]
        opening_price = round(wtp * rng.uniform(0.60, 0.85), -1)
        vendor, customer = VENDORS[0], ctx.customer

        lines = [f"MASTER SUBSCRIPTION AGREEMENT", "", f"Between {customer} (\"Customer\") and {vendor} (\"Vendor\").", ""]
        included = []
        opening_days = 30
        num = 1
        for ctype in CLAUSE_ORDER:
            options = by_type[ctype]
            safe = [o for o in options if o[2] == "low"]
            risky = [o for o in options if o[2] != "low"]
            if ctype in ("price", "other") or not risky:
                pick = rng.choice(options)
            else:
                # deal-breaker clauses are rarer than merely off-market commercial ones
                p_risky = (0.02 + 0.16 * aggressiveness) if any(o[3] for o in risky) else (0.05 + 0.5 * aggressiveness)
                pick = rng.choice(risky) if rng.random() < p_risky else rng.choice(safe)
            family, _, level, human, redl, heading, variants = pick
            text = _fill(rng.choice(variants), "Vendor", "Customer", opening_price, ctx.seats)
            if ctype == "payment_terms":
                opening_days = extract_payment_days(text) or 30
            lines += [f"{num}. {heading}", text, ""]
            included.append({"section": num, "family": family, "type": ctype, "level": level,
                             "requires_human": human, "redlinable": redl})
            num += 1
        cid = f"contract_{i:03d}"
        (contract_dir / f"{cid}.txt").write_text("\n".join(lines))
        contracts.append({
            "contract_id": cid,
            "context": ctx.model_dump(),
            "should_escalate": any(c["requires_human"] for c in included),
            "clauses": included,
            "hidden": {"wtp": round(wtp, 2), "persona": persona, "opening_price": opening_price, "opening_days": opening_days},
        })
    return contracts


def gen_crm(rng: random.Random, n: int) -> list[dict]:
    rows = []
    for i in range(n):
        ctx = sample_context(rng)
        wtp = sample_wtp(ctx, rng)
        won = rng.random() < 0.7
        if won:
            price = wtp * rng.uniform(0.82, 1.0)
        else:  # lost: we asked for more than they would pay
            price = wtp * rng.uniform(1.05, 1.4)
        rows.append({
            "deal_id": f"D{i:05d}", "segment": ctx.segment, "region": ctx.region, "product": ctx.product,
            "seats": ctx.seats, "list_price": ctx.list_price, "final_price": round(price, 2),
            "payment_days": rng.choice([30, 30, 45, 60]), "term_months": rng.choice([12, 12, 24, 36]),
            "won": won, "rounds": rng.randint(2, 9),
        })
    return rows


def main(seed: int = 7, n_contracts: int = 200, n_deals: int = 1500) -> None:
    rng = random.Random(seed)
    for d in ("labels", "contracts", "crm"):
        (DATA / d).mkdir(parents=True, exist_ok=True)

    clauses = gen_clause_labels(rng)
    with open(DATA / "labels" / "clauses.jsonl", "w") as f:
        for r in clauses:
            f.write(json.dumps(r) + "\n")

    contracts = gen_contracts(rng, n_contracts)
    with open(DATA / "labels" / "contracts.jsonl", "w") as f:
        for c in contracts:
            f.write(json.dumps(c) + "\n")

    deals = gen_crm(rng, n_deals)
    with open(DATA / "crm" / "deals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(deals[0]))
        w.writeheader()
        w.writerows(deals)

    esc = sum(c["should_escalate"] for c in contracts)
    print(f"clauses: {len(clauses)} | contracts: {len(contracts)} ({esc} should escalate) | CRM deals: {len(deals)}")


if __name__ == "__main__":
    main()
