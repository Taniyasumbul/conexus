"""RO2 on real contract text (CUAD).

Ground truth, in priority order:
  1. expert labels from the annotation tool (data/labels/expert_cuad.jsonl), when present
  2. CUAD proxy labels (category-derived, noisy - see conexus/datasets/cuad.py)

Modes compared (clause type given from CUAD, isolating the Risk Agent):
  rules                rule playbook only
  ml (synthetic)       TF-IDF+LR trained on the synthetic clause bank -> transfer to real text
  ml (CUAD, CV)        TF-IDF+LR trained on CUAD, 5-fold grouped by contract
  hybrid (synthetic)   rules + synthetic ML
  hybrid (CUAD, CV)    rules + CUAD ML (the deployable configuration once trained on real data)
  llm / hybrid+llm     optional, on a stratified sample (costs API calls)
Also: Contract Analyst clause-type accuracy on real text (no headings available).
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from sklearn.model_selection import GroupKFold

from ..agents.analyst import ContractAnalystAgent, TypeClassifier, keyword_classify
from ..agents.risk import LegalRiskAgent, RiskClassifier
from ..config import DATA, Settings
from ..datasets.cuad import load, split_of
from ..llm import LLM
from ..models import Clause, ClauseType
from .escalation_eval import prf

CUAD_PATH = DATA / "cuad" / "clauses.jsonl"
EXPERT_PATH = DATA / "labels" / "expert_cuad.jsonl"


def expert_labels(path: Path = EXPERT_PATH) -> dict[str, bool]:
    """clause id -> adjudicated expert requires_human (majority of annotators; ties dropped)."""
    if not path.exists():
        return {}
    votes: dict[str, list[bool]] = defaultdict(list)
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("requires_human") is not None:
                votes[r["clause_id"]].append(bool(r["requires_human"]))
    out = {}
    for cid, v in votes.items():
        yes = sum(v)
        if yes * 2 != len(v):
            out[cid] = yes * 2 > len(v)
    return out


def _clause(r: dict) -> Clause:
    return Clause(id=r["id"], type=ClauseType(r["type"]), text=r["text"])


def run(settings: Settings, llm: LLM | None = None, llm_limit: int = 60, max_rows: int | None = None, seed: int = 0) -> dict:
    rows = load(CUAD_PATH)
    if not rows:
        raise FileNotFoundError("data/cuad/clauses.jsonl missing - run `conexus fetch-cuad` first")
    experts = expert_labels()
    labelled = []
    for r in rows:
        y = experts.get(r["id"], r["proxy_human"])
        if y is not None:
            labelled.append({**r, "y": bool(y), "source": "expert" if r["id"] in experts else "proxy"})
    test_rows = [r for r in labelled if split_of(r["contract"]) == "test"]
    labelled = [r for r in labelled if split_of(r["contract"]) == "dev"]  # all CV / tuning on dev only
    if max_rows:
        random.Random(seed).shuffle(labelled)
        labelled = labelled[:max_rows]
    y = [r["y"] for r in labelled]

    # ---- analyst clause-type accuracy on real text (no headings) ----
    # keyword-only vs learned TypeClassifier (5-fold grouped by contract; synthetic bank added to training)
    syn_rows = [json.loads(l) for l in settings.clause_labels_path.read_text().splitlines() if l.strip()]
    type_kw = [keyword_classify("", r["text"])[0].value == r["type"] for r in labelled]
    type_learned = [False] * len(labelled)
    for tr, te in GroupKFold(n_splits=5).split(labelled, groups=[r["contract"] for r in labelled]):
        tc = TypeClassifier().fit([labelled[i]["text"] for i in tr] + [r["text"] for r in syn_rows],
                                  [labelled[i]["type"] for i in tr] + [r["type"] for r in syn_rows])
        an = ContractAnalystAgent(None, type_classifier=tc)
        for i in te:
            type_learned[i] = an.classify("", labelled[i]["text"])[0].value == labelled[i]["type"]
    type_n, type_ok = Counter(), Counter()
    for r, ok in zip(labelled, type_learned):
        type_n[r["type"]] += 1
        type_ok[r["type"]] += ok

    # ---- risk modes ----
    syn_clf = RiskClassifier.from_jsonl(settings.clause_labels_path)
    preds: dict[str, list[bool]] = {m: [None] * len(labelled) for m in
                                    ("rules", "ml (synthetic)", "ml (CUAD, CV)", "hybrid (synthetic)", "hybrid (CUAD, CV)")}
    rules_agent = LegalRiskAgent(settings, None, RiskClassifier(), mode="rules")
    ml_syn = LegalRiskAgent(settings, None, syn_clf, mode="ml")
    hy_syn = LegalRiskAgent(settings, None, syn_clf, mode="hybrid")
    for i, r in enumerate(labelled):
        c = _clause(r)
        preds["rules"][i] = rules_agent.assess(c).requires_human
        preds["ml (synthetic)"][i] = ml_syn.assess(c).requires_human
        preds["hybrid (synthetic)"][i] = hy_syn.assess(c).requires_human

    groups = [r["contract"] for r in labelled]
    for tr, te in GroupKFold(n_splits=5).split(labelled, groups=groups):
        clf = RiskClassifier().fit([labelled[i]["text"] for i in tr], [labelled[i]["y"] for i in tr])
        ml = LegalRiskAgent(settings, None, clf, mode="ml")
        hy = LegalRiskAgent(settings, None, clf, mode="hybrid")
        for i in te:
            c = _clause(labelled[i])
            preds["ml (CUAD, CV)"][i] = ml.assess(c).requires_human
            preds["hybrid (CUAD, CV)"][i] = hy.assess(c).requires_human

    results = {m: prf(y, p) for m, p in preds.items()}
    weighted = settings.model_copy(update={"escalation": settings.escalation.model_copy(update={"combine": "weighted"})})
    yw = [None] * len(labelled)
    for tr, te in GroupKFold(n_splits=5).split(labelled, groups=groups):
        clf = RiskClassifier().fit([labelled[i]["text"] for i in tr], [labelled[i]["y"] for i in tr])
        hy = LegalRiskAgent(weighted, None, clf, mode="hybrid")
        for i in te:
            yw[i] = hy.assess(_clause(labelled[i])).requires_human
    results["ablation: hybrid (CUAD, CV), weighted average"] = prf(y, yw)

    # ---- which deal-breaker categories each mode misses ----
    by_cat = defaultdict(lambda: defaultdict(int))
    for i, r in enumerate(labelled):
        if not r["y"]:
            continue
        cat = next((c for c in r["categories"] if c in ("Uncapped Liability", "Ip Ownership Assignment", "Non-Compete", "Exclusivity")), r["categories"][0])
        by_cat[cat]["n"] += 1
        for m in ("rules", "hybrid (CUAD, CV)"):
            by_cat[cat][m] += preds[m][i]
    recall_by_category = [{"category": c, "n": v["n"], "rules_recall": round(v["rules"] / v["n"], 3),
                           "hybrid_cuad_recall": round(v["hybrid (CUAD, CV)"] / v["n"], 3)} for c, v in sorted(by_cat.items())]

    # ---- held-out test: train on all dev contracts, score the untouched test contracts once ----
    held_out = {}
    if test_rows:
        yt = [r["y"] for r in test_rows]
        dev_clf = RiskClassifier().fit([r["text"] for r in labelled], [r["y"] for r in labelled])
        for name, agent in (("rules", rules_agent),
                            ("ml (CUAD dev)", LegalRiskAgent(settings, None, dev_clf, mode="ml")),
                            ("hybrid (CUAD dev)", LegalRiskAgent(settings, None, dev_clf, mode="hybrid"))):
            held_out[name] = prf(yt, [agent.assess(_clause(r)).requires_human for r in test_rows])

    # ---- optional LLM on a stratified sample of the held-out test contracts ----
    if llm is not None:
        rng = random.Random(seed)
        pool = test_rows or labelled
        pos = [r for r in pool if r["y"]]
        neg = [r for r in pool if not r["y"]]
        k = llm_limit // 2
        sample = rng.sample(pos, min(k, len(pos))) + rng.sample(neg, min(k, len(neg)))
        dev_clf = RiskClassifier().fit([r["text"] for r in labelled], [r["y"] for r in labelled])
        ys = [r["y"] for r in sample]
        for mode, clf in (("hybrid", dev_clf), ("llm", RiskClassifier()), ("hybrid+llm", dev_clf)):
            agent = LegalRiskAgent(settings, llm if "llm" in mode else None, clf, mode=mode)
            yp = [agent.assess(_clause(r)).requires_human for r in sample]
            held_out[f"{mode} (test sample n={len(sample)}, {llm.name})"] = prf(ys, yp)

    return {
        "n_clauses": len(labelled), "n_contracts": len(set(groups)),
        "held_out_test": held_out, "n_test_clauses": len(test_rows),
        "n_test_contracts": len({r["contract"] for r in test_rows}),
        "positives": sum(y), "expert_labelled": sum(r["source"] == "expert" for r in labelled),
        "results": results, "recall_by_category": recall_by_category,
        "analyst_type_accuracy": {"keywords": round(sum(type_kw) / len(type_kw), 3),
                                  "learned (CV)": round(sum(type_learned) / len(type_learned), 3)},
        "analyst_type_accuracy_by_type": {t: round(type_ok[t] / type_n[t], 3) for t in sorted(type_n)},
    }
