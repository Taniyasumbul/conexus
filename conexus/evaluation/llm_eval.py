"""LLM experiments.

1. Reply-parsing robustness: can the Communication Agent read what customers actually
   write? Ground-truth offers are rendered through hand-written phrasing styles, from
   regex-friendly ("$18,500 ... net 45") to natural ("18.5k, payment in 45 days"), then
   parsed by regex and by the LLM. Phrasings are written by us, not by the model, so the
   model is never grading its own paraphrases.
2. Risk scoring on held-out CUAD contracts (delegates to cuad_eval with an LLM).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..agents.communication import CommunicationAgent
from ..llm import LLM

WORDS = {12000: "twelve thousand", 15000: "fifteen thousand", 18500: "eighteen thousand five hundred",
         21000: "twenty-one thousand", 24750: "twenty-four thousand seven hundred and fifty", 9800: "nine thousand eight hundred"}


@dataclass
class Case:
    style: str
    text: str
    price: float | None
    days: int | None
    accept: bool
    redlines: dict[str, bool]


def _k(p: float) -> str:
    return f"{p / 1000:g}k"


STYLES = {
    # regex-friendly: what our template counterparty writes
    "template": lambda p, d, rl: f"Our counter-proposal is ${p:,.0f} per year with payment net {d} days." + "".join(
        f" We {'accept' if ok else 'cannot accept'} the change to clause {c}." for c, ok in rl.items()),
    "shorthand": lambda p, d, rl: f"Can do {_k(p)} annually if we get {d}-day terms." + "".join(
        f" {'Fine with' if ok else 'No to'} your edit on {c}." for c, ok in rl.items()),
    "words": lambda p, d, rl: f"We could stretch to {WORDS.get(round(p), f'{p:,.0f} dollars')} dollars a year, paid within {d} days of invoice." + "".join(
        f" Clause {c[1:]}: {'agreed' if ok else 'we have to push back'}." for c, ok in rl.items()),
    "email": lambda p, d, rl: f"Hi team,\n\nThanks for the revised draft. Finance has signed off on USD {p:,.0f}/yr; "
                              f"they need payment terms of {d} days though.\n" + "".join(
        f"\nOn section {c[1:]}, {'your wording works for us' if ok else 'legal will not move on this one'}." for c, ok in rl.items())
                              + "\n\nBest,\nProcurement",
    "indian_english": lambda p, d, rl: f"Kindly note we can do Rs-equivalent of USD {p:,.0f} per annum only, with {d} days credit period." + "".join(
        f" Point {c[1:]} {'is okay' if ok else 'is not acceptable'} from our side." for c, ok in rl.items()),
}
ACCEPTS = [
    "We accept your proposal of ${p:,.0f} per year, net {d}. Deal.",
    "Done - ${p:,.0f} works, net {d}. Please send the paperwork.",
    "Okay, let's close at {k} with {d}-day payment. Send it for signature.",
]


def build_cases(n_per_style: int = 8, seed: int = 0) -> list[Case]:
    rng = random.Random(seed)
    prices = list(WORDS)
    cases = []
    for style, fn in STYLES.items():
        for _ in range(n_per_style):
            p, d = rng.choice(prices), rng.choice([30, 45, 60, 90])
            rl = {f"c{rng.randint(2, 13)}": rng.random() < 0.5} if rng.random() < 0.7 else {}
            cases.append(Case(style, fn(p, d, rl), p, d, False, rl))
    for i, tpl in enumerate(ACCEPTS * 2):
        p, d = rng.choice(prices), rng.choice([30, 45])
        cases.append(Case("acceptance", tpl.format(p=p, d=d, k=_k(p)), p if "{p" in tpl or "{k" in tpl else None, d, True, {}))
    return cases


def _score(case: Case, o) -> dict[str, bool]:
    price_ok = case.price is None or (o.terms is not None and abs(o.terms.price - case.price) <= 0.01 * case.price) or (case.accept and o.accept)
    days_ok = case.accept or (o.terms is not None and o.terms.payment_days == case.days)
    return {"price": price_ok, "days": days_ok, "accept": o.accept == case.accept,
            "redlines": all(o.redline_responses.get(c) == ok for c, ok in case.redlines.items()),
            "all": False}


def parsing_robustness(llm: LLM | None, n_per_style: int = 8, seed: int = 0) -> dict:
    cases = build_cases(n_per_style, seed)
    parsers = {"regex": CommunicationAgent(None)}
    if llm is not None:
        parsers[f"llm ({llm.name})"] = CommunicationAgent(llm)
    out = {}
    for name, agent in parsers.items():
        by_style: dict[str, list[dict]] = {}
        t0 = time.perf_counter()
        for c in cases:
            o = agent.parse(c.text, 1, list(c.redlines))
            s = _score(c, o)
            s["all"] = s["price"] and s["days"] and s["accept"] and s["redlines"]
            by_style.setdefault(c.style, []).append(s)
        dt = (time.perf_counter() - t0) / len(cases)
        out[name] = {
            "overall": round(sum(s["all"] for v in by_style.values() for s in v) / len(cases), 3),
            "by_style": {st: round(sum(s["all"] for s in v) / len(v), 3) for st, v in by_style.items()},
            "fields": {f: round(sum(s[f] for v in by_style.values() for s in v) / len(cases), 3) for f in ("price", "days", "accept", "redlines")},
            "sec_per_message": round(dt, 3),
        }
    return {"n_messages": len(cases), "styles": list(STYLES) + ["acceptance"], "results": out,
            "examples": {st: next(c.text for c in cases if c.style == st) for st in list(STYLES) + ["acceptance"]}}
