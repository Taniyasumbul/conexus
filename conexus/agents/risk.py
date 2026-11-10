"""Legal/Risk Agent (RO2): clause-level risk scoring + redline recommendation.

Three signals, combined into a hybrid score:
  1. rules  - transparent regex playbook encoding the annotation guideline.
              "Hard" rules force escalation regardless of score.
  2. ml     - TF-IDF + logistic regression trained on labelled clauses
              (P(requires_human)); generalises beyond exact wording.
  3. llm    - optional structured assessment from Claude / Ollama.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from ..config import Settings
from ..llm import LLM, LLMError
from ..models import Clause, ClauseRisk, ClauseType, RiskLevel


@dataclass
class Rule:
    type: ClauseType | None
    pattern: str
    level: RiskLevel
    hard: bool  # requires a human regardless of other signals
    redlinable: bool
    reason: str
    regex: re.Pattern = field(init=False)

    def __post_init__(self):
        self.regex = re.compile(self.pattern, re.IGNORECASE | re.DOTALL)


H, M = RiskLevel.HIGH, RiskLevel.MEDIUM
RULES = [
    Rule(ClauseType.LIABILITY_CAP, r"unlimited|without limit|shall not apply to (the )?vendor|nothing herein shall limit", H, True, True, "Uncapped vendor liability"),
    Rule(ClauseType.LIABILITY_CAP, r"(ten|five|\d{2,})\s*(\(\d+\)\s*)?times", H, True, True, "Liability cap far above market (>2x fees)"),
    Rule(ClauseType.LIABILITY_CAP, r"consequential damages shall apply only to", H, True, True, "One-sided exclusion of consequential damages"),
    Rule(ClauseType.INDEMNIFICATION, r"(own|customer'?s) negligence|regardless of (fault|whether)|howsoever arising|any and all (claims|liabilities)", H, True, False, "One-sided / unlimited indemnity incl. counterparty's own fault"),
    Rule(ClauseType.IP_OWNERSHIP, r"pre-existing|background ip|know-how|tools.*(assign|vest)|improvements .* exclusive property|(assign|vest).*(software|platform)", H, True, False, "Transfer of vendor background IP / platform improvements"),
    Rule(None, r"shall not\b.{0,60}?(provide|license|develop|market).*(competitor|compet|other company)|exclusivity", H, True, False, "Exclusivity / non-compete binding the vendor"),
    Rule(ClauseType.DATA_PROTECTION, r"strictly liable|howsoever caused|bear all regulatory fines", H, True, False, "Strict liability for data breaches / fines"),
    Rule(ClauseType.DATA_PROTECTION, r"audit .* at any time without notice", H, True, False, "Unlimited, unannounced audit rights"),
    Rule(ClauseType.PAYMENT_TERMS, r"\b(90|120)\b|ninety|one hundred and twenty|sole discretion|withhold payment", H, False, True, "Payment terms >= 90 days or discretionary"),
    Rule(ClauseType.PAYMENT_TERMS, r"\b(45|60)\b|sixty|no late payment", M, False, True, "Payment terms longer than policy (30 days)"),
    Rule(ClauseType.TERMINATION, r"for convenience|without cause", H, False, True, "Customer termination for convenience with refund"),
    Rule(ClauseType.AUTO_RENEWAL, r"may not increase|fixed .* (five|\d) .*years", M, False, True, "Price lock on renewal"),
    Rule(ClauseType.GOVERNING_LAW, r"new york|england|singapore|delaware|california", M, False, True, "Foreign governing law / forum"),
    Rule(ClauseType.WARRANTY, r"100%|error-free|every purpose|50% of annual", H, False, True, "Absolute warranty / punitive service credits"),
    Rule(ClauseType.CONFIDENTIALITY, r"in perpetuity|indefinitely|bind .*vendor only|no confidentiality obligations", M, False, True, "One-sided or perpetual confidentiality"),
    Rule(ClauseType.ASSIGNMENT, r"may assign this agreement freely", M, False, True, "One-sided assignment right"),
]

REDLINES: dict[ClauseType, str] = {
    ClauseType.PAYMENT_TERMS: "Customer shall pay undisputed invoices within thirty (30) days of the invoice date.",
    ClauseType.LIABILITY_CAP: "Each party's aggregate liability shall not exceed the fees paid in the twelve (12) months preceding the claim; neither party is liable for indirect or consequential damages.",
    ClauseType.TERMINATION: "Either party may terminate for uncured material breach on thirty (30) days' notice. Prepaid fees are non-refundable except on Vendor's breach.",
    ClauseType.AUTO_RENEWAL: "Renewal fees may increase by no more than 7% per year.",
    ClauseType.GOVERNING_LAW: "This Agreement is governed by the laws of India, with arbitration seated in New Delhi.",
    ClauseType.WARRANTY: "Vendor shall use commercially reasonable efforts to achieve 99.5% availability; service credits capped at 10% of monthly fees.",
    ClauseType.CONFIDENTIALITY: "Confidentiality obligations are mutual and survive for three (3) years.",
    ClauseType.ASSIGNMENT: "Neither party may assign without consent, except to a successor in a merger or acquisition.",
}

LEVEL_SCORE = {RiskLevel.LOW: 0.05, RiskLevel.MEDIUM: 0.3, RiskLevel.HIGH: 0.45}  # non-hard rules never escalate alone


class _LLMAssessment(BaseModel):
    level: RiskLevel
    requires_human: bool
    reasons: list[str]


class RiskClassifier:
    """TF-IDF + logistic regression for P(requires_human)."""

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline

        self.pipe = make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1),
            LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0),
        )
        self.fitted = False

    def fit(self, texts: list[str], labels: list[bool]) -> "RiskClassifier":
        if len(set(labels)) > 1:
            self.pipe.fit(texts, labels)
            self.fitted = True
        return self

    def predict_proba(self, text: str) -> float | None:
        if not self.fitted:
            return None
        return float(self.pipe.predict_proba([text])[0][1])

    @classmethod
    def from_jsonl(cls, path: Path) -> "RiskClassifier":
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()] if Path(path).exists() else []
        return cls().fit([r["text"] for r in rows], [r["requires_human"] for r in rows])


class LegalRiskAgent:
    name = "legal_risk"

    def __init__(self, settings: Settings, llm: LLM | None = None, classifier: RiskClassifier | None = None,
                 mode: str = "hybrid"):
        """mode: rules | ml | hybrid | llm | hybrid+llm"""
        self.s = settings
        self.llm = llm
        self.mode = mode
        self.clf = classifier if classifier is not None else RiskClassifier.from_jsonl(settings.clause_labels_path)

    def apply_rules(self, clause: Clause) -> tuple[RiskLevel, bool, bool, list[str]]:
        level, hard, redl, reasons = RiskLevel.LOW, False, False, []
        for r in RULES:
            if r.type is not None and r.type != clause.type:
                continue
            if r.regex.search(clause.text):
                reasons.append(r.reason)
                hard = hard or r.hard
                redl = redl or r.redlinable
                if LEVEL_SCORE[r.level] > LEVEL_SCORE[level]:
                    level = r.level
        return level, hard, redl, reasons

    def assess(self, clause: Clause) -> ClauseRisk:
        level, hard, redl, reasons = self.apply_rules(clause)
        rule_score = 0.95 if hard else LEVEL_SCORE[level]
        ml = self.clf.predict_proba(clause.text) if self.mode != "rules" else None
        w = self.s.escalation.ml_weight

        if self.mode == "rules" or ml is None:
            score = rule_score
        elif self.mode == "ml":
            score, hard = ml, False
        else:
            score = (1 - w) * rule_score + w * ml
        source = self.mode

        if self.llm and self.mode in ("llm", "hybrid+llm"):
            try:
                a = self.llm.structured(
                    "You are a contracts lawyer advising a small software vendor with no in-house legal team. "
                    "Assess the risk of this customer-drafted clause to the VENDOR. requires_human=true only if the "
                    "clause creates exposure the vendor cannot price or reverse (uncapped liability, one-sided "
                    "indemnity, loss of background IP, exclusivity, strict liability for data breaches, unlimited audits).",
                    f"Clause type: {clause.type.value}\nClause: {clause.text}",
                    _LLMAssessment,
                )
                llm_score = 0.9 if a.requires_human else LEVEL_SCORE[a.level]
                score = llm_score if self.mode == "llm" else max(score, llm_score)
                if self.mode == "llm":
                    hard, level = False, a.level
                reasons += [f"LLM: {r}" for r in a.reasons]
                if LEVEL_SCORE[a.level] > LEVEL_SCORE[level]:
                    level = a.level
            except LLMError as e:
                reasons.append(f"LLM unavailable ({e}); fell back to {self.mode.replace('+llm', '')}")

        requires_human = hard or score >= self.s.escalation.clause_threshold
        if score >= 0.5 and level == RiskLevel.LOW:
            level = RiskLevel.MEDIUM
        redlinable = redl and clause.type in REDLINES
        return ClauseRisk(
            clause_id=clause.id, clause_type=clause.type, level=level, score=round(score, 3),
            requires_human=requires_human, redlinable=redlinable,
            redline=REDLINES.get(clause.type) if (redlinable or level != RiskLevel.LOW) else None,
            reasons=reasons, source=source,
        )

    def assess_all(self, clauses: list[Clause]) -> list[ClauseRisk]:
        return [self.assess(c) for c in clauses]
