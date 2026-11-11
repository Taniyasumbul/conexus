"""CUAD (Contract Understanding Atticus Dataset) -> CoNexus clause benchmark.

CUAD v1: 510 real commercial contracts from SEC EDGAR, with spans highlighted by
lawyers for 41 categories (CC BY 4.0, Hendrycks et al., NeurIPS 2021).
Get it with:  conexus fetch-cuad   (or download data.zip from github.com/TheAtticusProject/cuad)

Each highlighted span becomes one clause row with:
  type            our ClauseType, mapped from the CUAD category
  proxy_human     weak "requires a human" label from the category (see PROXY);
                  None = ambiguous, left for expert annotation
  contract        source contract (used for grouped train/test splits)

Proxy labels are weak supervision: CUAD does not record which party a clause
binds, so e.g. an "Uncapped Liability" span may be uncapped for the *customer*.
Expert labels collected in the annotation tool override them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# CUAD category -> (our clause type, proxy requires_human: True / False / None=ambiguous)
CATEGORY_MAP: dict[str, tuple[str, bool | None]] = {
    # deal-breakers under the annotation guideline
    "Uncapped Liability": ("liability_cap", True),
    "Ip Ownership Assignment": ("ip_ownership", True),
    "Non-Compete": ("non_compete", True),
    "Exclusivity": ("non_compete", True),
    # standard / commercial
    "Cap On Liability": ("liability_cap", False),
    "Governing Law": ("governing_law", False),
    "Anti-Assignment": ("assignment", False),
    "Change Of Control": ("assignment", False),
    "Renewal Term": ("auto_renewal", False),
    "Notice Period To Terminate Renewal": ("auto_renewal", False),
    "Termination For Convenience": ("termination", False),
    "Post-Termination Services": ("termination", False),
    "Warranty Duration": ("warranty", False),
    "Audit Rights": ("data_protection", False),
    "Insurance": ("other", False),
    "License Grant": ("ip_ownership", False),
    "Non-Transferable License": ("ip_ownership", False),
    "Affiliate License-Licensee": ("ip_ownership", False),
    "Affiliate License-Licensor": ("ip_ownership", False),
    "No-Solicit Of Employees": ("non_compete", False),
    "Non-Disparagement": ("other", False),
    "Third Party Beneficiary": ("other", False),
    "Minimum Commitment": ("price", False),
    "Revenue/Profit Sharing": ("price", False),
    "Volume Restriction": ("price", False),
    # ambiguous without knowing the party / context -> expert annotation pool
    "Joint Ip Ownership": ("ip_ownership", None),
    "Irrevocable Or Perpetual License": ("ip_ownership", None),
    "Unlimited/All-You-Can-Eat-License": ("ip_ownership", None),
    "Source Code Escrow": ("ip_ownership", None),
    "Covenant Not To Sue": ("other", None),
    "Liquidated Damages": ("liability_cap", None),
    "Most Favored Nation": ("price", None),
    "Price Restrictions": ("price", None),
    "No-Solicit Of Customers": ("non_compete", None),
    "Competitive Restriction Exception": ("non_compete", None),
    "Rofr/Rofo/Rofn": ("other", None),
}
METADATA = {"Parties", "Document Name", "Agreement Date", "Effective Date", "Expiration Date"}
MIN_CHARS, MAX_CHARS = 60, 1500


def build(raw_json: Path, out_path: Path) -> dict:
    """Convert CUADv1.json (SQuAD format) into data/cuad/clauses.jsonl."""
    data = json.loads(Path(raw_json).read_text())["data"]
    rows: dict[str, dict] = {}
    for doc in data:
        title = doc["title"]
        for para in doc["paragraphs"]:
            for qa in para["qas"]:
                cat = qa["id"].split("__")[-1]
                if cat in METADATA or cat not in CATEGORY_MAP:
                    continue
                ctype, proxy = CATEGORY_MAP[cat]
                for ans in qa["answers"]:
                    text = " ".join(ans["text"].split())
                    if not (MIN_CHARS <= len(text) <= MAX_CHARS):
                        continue
                    key = hashlib.sha1(f"{title}|{text}".encode()).hexdigest()[:12]
                    row = rows.get(key)
                    if row is None:
                        rows[key] = {"id": f"cuad-{key}", "contract": title, "categories": [cat], "type": ctype,
                                     "proxy_human": proxy, "text": text}
                    else:  # same span tagged with several categories: any True wins, else any False, else None
                        row["categories"].append(cat)
                        if proxy is True or row["proxy_human"] is None and proxy is False:
                            row["proxy_human"], row["type"] = proxy, ctype
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for r in rows.values():
            f.write(json.dumps(r) + "\n")
    vals = list(rows.values())
    return {
        "contracts": len({r["contract"] for r in vals}), "clauses": len(vals),
        "proxy_true": sum(r["proxy_human"] is True for r in vals),
        "proxy_false": sum(r["proxy_human"] is False for r in vals),
        "ambiguous": sum(r["proxy_human"] is None for r in vals),
    }


def split_of(contract: str) -> str:
    """Stable 80/20 dev/test split by contract (hash-based, never changes).
    Tune and train on "dev" only; report "test" once."""
    return "test" if int(hashlib.sha1(contract.encode()).hexdigest(), 16) % 5 == 0 else "dev"


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()] if Path(path).exists() else []
