"""Expert annotation service (RO2 ground truth on real contracts).

- Queue: a fixed, seeded, stratified sample of CUAD clauses (ambiguous, proxy-positive
  and proxy-negative interleaved), so every annotator works through the same order.
- Overlap first: clauses already labelled by someone else are offered before new ones,
  so inter-annotator agreement (Cohen's kappa) can be computed.
- No anchoring: /next returns only the clause text; the CUAD category, proxy label and
  model score are returned by POST (the reveal) after the annotator commits a label.
- Every label is exported to data/labels/expert_cuad.jsonl, which eval-cuad and the
  default risk model read (expert labels override proxy labels).
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from ..agents.risk import LegalRiskAgent
from ..config import DATA, Settings
from ..datasets.cuad import load
from ..models import Clause, ClauseType
from ..store import Store

EXPORT = DATA / "labels" / "expert_cuad.jsonl"


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


class AnnotationService:
    def __init__(self, settings: Settings, store: Store, risk: LegalRiskAgent, per_stratum: int = 200, seed: int = 13,
                 export_path: Path = EXPORT):
        self.s, self.store, self.risk, self.export_path = settings, store, risk, Path(export_path)
        rows = load(DATA / "cuad" / "clauses.jsonl")
        self.by_id = {r["id"]: r for r in rows}
        rng = random.Random(seed)
        strata = [[r for r in rows if r["proxy_human"] is None], [r for r in rows if r["proxy_human"] is True],
                  [r for r in rows if r["proxy_human"] is False]]
        picks = [rng.sample(s, min(per_stratum, len(s))) for s in strata]
        self.queue = [r["id"] for trio in zip(*picks) for r in trio]

    @property
    def available(self) -> bool:
        return bool(self.queue)

    def _labels(self) -> dict[str, dict[str, bool | None]]:
        out: dict[str, dict[str, bool | None]] = defaultdict(dict)
        for a in self.store.annotations():
            out[a["clause_id"]][a["annotator"]] = None if a["requires_human"] is None else bool(a["requires_human"])
        return out

    def next(self, annotator: str) -> dict | None:
        labels = self._labels()
        mine = {cid for cid, v in labels.items() if annotator in v}
        overlap = [cid for cid in self.queue if cid in labels and cid not in mine]
        fresh = [cid for cid in self.queue if cid not in labels]
        cid = (overlap or fresh or [None])[0]
        if cid is None:
            return None
        r = self.by_id[cid]
        return {"clause_id": cid, "text": r["text"], "contract": r["contract"].replace("_", " "),
                "type": r["type"], "position": len(mine) + 1, "queue_size": len(self.queue),
                "labelled_by_others": len(labels.get(cid, {}))}

    def submit(self, clause_id: str, annotator: str, requires_human: bool | None, level: str | None,
               redlinable: bool | None, note: str) -> dict:
        r = self.by_id.get(clause_id)
        if r is None:
            raise KeyError(clause_id)
        self.store.annotate(clause_id, annotator, requires_human, level, redlinable, note)
        self.export()
        assessed = self.risk.assess(Clause(id=clause_id, type=ClauseType(r["type"]), text=r["text"]))
        return {"categories": r["categories"], "proxy_human": r["proxy_human"],
                "model": {"requires_human": assessed.requires_human, "score": assessed.score, "reasons": assessed.reasons}}

    def export(self) -> int:
        rows = self.store.annotations()
        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.export_path, "w") as f:
            for a in rows:
                f.write(json.dumps({"clause_id": a["clause_id"], "annotator": a["annotator"],
                                    "requires_human": None if a["requires_human"] is None else bool(a["requires_human"]),
                                    "level": a["level"], "redlinable": None if a["redlinable"] is None else bool(a["redlinable"]),
                                    "note": a["note"], "ts": a["ts"]}) + "\n")
        return len(rows)

    def stats(self) -> dict:
        labels = self._labels()
        per_annotator: dict[str, int] = defaultdict(int)
        for v in labels.values():
            for who in v:
                per_annotator[who] += 1
        # pairwise kappa on clauses both annotators labelled (skips excluded)
        pairs = []
        for a, b in combinations(sorted(per_annotator), 2):
            both = [(v[a], v[b]) for v in labels.values() if v.get(a) is not None and v.get(b) is not None]
            pairs.append({"a": a, "b": b, "overlap": len(both),
                          "agreement": round(sum(x == y for x, y in both) / len(both), 3) if both else None,
                          "kappa": cohen_kappa([x for x, _ in both], [y for _, y in both])})
        # majority label vs proxy and vs model
        maj, vs_proxy, vs_model = {}, [], []
        for cid, v in labels.items():
            votes = [x for x in v.values() if x is not None]
            if votes and sum(votes) * 2 != len(votes):
                maj[cid] = sum(votes) * 2 > len(votes)
        for cid, y in maj.items():
            r = self.by_id[cid]
            if r["proxy_human"] is not None:
                vs_proxy.append(r["proxy_human"] == y)
            pred = self.risk.assess(Clause(id=cid, type=ClauseType(r["type"]), text=r["text"])).requires_human
            vs_model.append(pred == y)
        return {
            "queue_size": len(self.queue), "clauses_labelled": len(labels),
            "labels": sum(per_annotator.values()), "per_annotator": dict(per_annotator),
            "pairs": pairs, "adjudicated": len(maj), "positives": sum(maj.values()),
            "proxy_agreement": round(sum(vs_proxy) / len(vs_proxy), 3) if vs_proxy else None,
            "model_agreement": round(sum(vs_model) / len(vs_model), 3) if vs_model else None,
            "export_path": str(self.export_path),
        }
