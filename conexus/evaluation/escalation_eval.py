"""RO2: precision / recall of the risk-gated escalation policy.

Part A (clause level): grouped K-fold over *template families*, so the ML
component is always tested on wording families it never saw in training.
Gold clause types are given, isolating the Legal/Risk Agent.

Part B (contract level, end to end): Analyst -> Risk -> gate on full contracts.
Positive = contract contains >= 1 clause an expert says needs a human.
Predicted positive = system flags >= 1 clause as requires_human.

Part C: threshold sweep of the hybrid score (precision/recall trade-off).
"""
from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
from sklearn.model_selection import GroupKFold

from ..agents.risk import LegalRiskAgent, RiskClassifier
from ..config import DATA, Settings
from ..llm import LLM
from ..models import Clause, ClauseType, DealContext
from ..orchestrator import Orchestrator


def prf(y_true: list[bool], y_pred: list[bool]) -> dict:
    tp = sum(t and p for t, p in zip(y_true, y_pred))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred))
    tn = len(y_true) - tp - fp - fn
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def load_clauses() -> list[dict]:
    return [json.loads(l) for l in (DATA / "labels" / "clauses.jsonl").read_text().splitlines() if l.strip()]


def load_contracts() -> list[dict]:
    return [json.loads(l) for l in (DATA / "labels" / "contracts.jsonl").read_text().splitlines() if l.strip()]


def clause_level(settings: Settings, modes=("rules", "ml", "hybrid"), llm: LLM | None = None,
                 folds: int = 5, llm_limit: int = 60) -> dict:
    rows = load_clauses()
    groups = [r["family"] for r in rows]
    preds: dict[str, list[bool]] = defaultdict(list)
    truth: list[bool] = []
    scores: list[float] = []
    for tr, te in GroupKFold(n_splits=folds).split(rows, groups=groups):
        clf = RiskClassifier().fit([rows[i]["text"] for i in tr], [rows[i]["requires_human"] for i in tr])
        for i in te:
            r = rows[i]
            clause = Clause(id=r["id"], type=ClauseType(r["type"]), text=r["text"])
            truth.append(r["requires_human"])
            for m in modes:
                a = LegalRiskAgent(settings, None, clf, mode=m).assess(clause)
                preds[m].append(a.requires_human)
                if m == "hybrid":
                    scores.append(a.score)
    out = {m: prf(truth, preds[m]) for m in modes}

    if llm is not None:  # LLM-only and hybrid+LLM on a stratified sample (cost control)
        rng = np.random.default_rng(0)
        pos = [r for r in rows if r["requires_human"]]
        neg = [r for r in rows if not r["requires_human"]]
        k = llm_limit // 2
        sample = list(rng.choice(pos, min(k, len(pos)), replace=False)) + list(rng.choice(neg, min(k, len(neg)), replace=False))
        clf = RiskClassifier().fit([r["text"] for r in rows], [r["requires_human"] for r in rows])
        for m in ("llm",):
            agent = LegalRiskAgent(settings, llm, clf, mode=m)
            yp = [agent.assess(Clause(id=r["id"], type=ClauseType(r["type"]), text=r["text"])).requires_human for r in sample]
            out[f"{m} (n={len(sample)})"] = prf([r["requires_human"] for r in sample], yp)

    sweep = []
    for th in np.linspace(0.1, 0.9, 9):
        sweep.append({"threshold": round(float(th), 2), **prf(truth, [s >= th for s in scores])})
    return {"clause_level": out, "hybrid_threshold_sweep_scores_only": sweep, "n_clauses": len(truth)}


class CrossFitClassifier:
    """Scores each clause with a model trained WITHOUT that clause's template family
    (out-of-fold prediction), so contract-level numbers are not inflated by leakage."""

    def __init__(self, rows: list[dict], folds: int = 5):
        groups = [r["family"] for r in rows]
        self.family_model: dict[str, RiskClassifier] = {}
        for tr, te in GroupKFold(n_splits=folds).split(rows, groups=groups):
            clf = RiskClassifier().fit([rows[i]["text"] for i in tr], [rows[i]["requires_human"] for i in tr])
            for i in te:
                self.family_model[rows[i]["family"]] = clf
        self.current_family: str | None = None
        self.fitted = True

    def predict_proba(self, text: str) -> float | None:
        clf = self.family_model.get(self.current_family)
        return clf.predict_proba(text) if clf else None


def contract_level(settings: Settings, modes=("rules", "ml", "hybrid"), llm: LLM | None = None, limit: int | None = None) -> dict:
    contracts = load_contracts()[:limit]
    out = {}
    clf = CrossFitClassifier(load_clauses())
    for m in modes:
        orch = Orchestrator(settings, llm if "llm" in m else None, risk_mode=m, classifier=clf)
        y, yp, gate_only = [], [], []
        type_correct = type_total = 0
        for c in contracts:
            text = (DATA / "contracts" / f"{c['contract_id']}.txt").read_text()
            gold = {f"c{cl['section']}": cl for cl in c["clauses"]}
            st = orch.analyze(c["contract_id"], text, DealContext(**c["context"]))
            # re-score each clause with its out-of-fold model
            risks = []
            for cl in st.clauses:
                clf.current_family = gold.get(cl.id, {}).get("family")
                risks.append(orch.risk.assess(cl))
                if cl.id in gold:
                    type_total += 1
                    type_correct += cl.type.value == gold[cl.id]["type"]
            st.risks = risks
            y.append(c["should_escalate"])
            yp.append(any(r.requires_human for r in st.risks))
            gate_only.append(orch.pre_negotiation_gate(st).escalate)
        out[m] = {**prf(y, yp), "immediate_escalations": int(sum(gate_only)),
                  "analyst_type_accuracy": round(type_correct / max(1, type_total), 3)}
    return {"contract_level": out, "n_contracts": len(contracts),
            "positives": int(sum(c["should_escalate"] for c in contracts))}
