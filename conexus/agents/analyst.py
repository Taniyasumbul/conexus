"""Contract Analyst Agent: document -> typed clauses + the counterparty's opening terms."""
from __future__ import annotations

import re

from pydantic import BaseModel

from ..llm import LLM, LLMError
from ..models import Clause, ClauseType, Terms
from ..parsing import split_sections

KEYWORDS: dict[ClauseType, list[str]] = {
    ClauseType.PAYMENT_TERMS: ["invoice", "payable", "net ", "payment", "days of receipt", "late"],
    ClauseType.PRICE: ["subscription fee", "annual fees", "total annual", "named users", "user seats"],
    ClauseType.LIABILITY_CAP: ["liability", "liable", "consequential", "aggregate", "cap"],
    ClauseType.INDEMNIFICATION: ["indemnif", "hold harmless", "defend"],
    ClauseType.IP_OWNERSHIP: ["intellectual property", "title and interest", "assign", "derivative works", "background ip", "licence"],
    ClauseType.CONFIDENTIALITY: ["confidential"],
    ClauseType.TERMINATION: ["terminat"],
    ClauseType.AUTO_RENEWAL: ["renew"],
    ClauseType.GOVERNING_LAW: ["governed by", "jurisdiction", "arbitration", "laws of"],
    ClauseType.WARRANTY: ["warrant", "uptime", "error-free", "fit for"],
    ClauseType.NON_COMPETE: ["compet", "exclusiv", "solicit"],
    ClauseType.DATA_PROTECTION: ["personal data", "data breach", "audit", "dpdp", "gdpr"],
    ClauseType.ASSIGNMENT: ["assign this agreement", "subcontract", "may assign"],
}
HEADING_HINTS: dict[str, ClauseType] = {
    "payment": ClauseType.PAYMENT_TERMS, "fee": ClauseType.PRICE, "liabil": ClauseType.LIABILITY_CAP,
    "indemn": ClauseType.INDEMNIFICATION, "intellectual": ClauseType.IP_OWNERSHIP, "confiden": ClauseType.CONFIDENTIALITY,
    "terminat": ClauseType.TERMINATION, "renew": ClauseType.AUTO_RENEWAL, "governing": ClauseType.GOVERNING_LAW,
    "warrant": ClauseType.WARRANTY, "exclusiv": ClauseType.NON_COMPETE, "non-solic": ClauseType.NON_COMPETE,
    "non-compet": ClauseType.NON_COMPETE, "data": ClauseType.DATA_PROTECTION, "assign": ClauseType.ASSIGNMENT,
}

_WORD_NUM = {"thirty": 30, "forty-five": 45, "sixty": 60, "ninety": 90, "one hundred and twenty": 120}


class _LLMClauseType(BaseModel):
    type: ClauseType
    confidence: float


def keyword_classify(heading: str, text: str) -> tuple[ClauseType, float]:
    h = heading.lower()
    for hint, t in HEADING_HINTS.items():
        if hint in h:
            return t, 0.9
    low = text.lower()
    scores = {t: sum(low.count(k) for k in kws) for t, kws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] == 0:
        return ClauseType.OTHER, 0.3
    return best, scores[best] / total


def extract_payment_days(text: str) -> int | None:
    low = text.lower()
    m = re.search(r"net\s*(\d{2,3})", low) or re.search(r"\((\d{2,3})\)\s*days", low) or re.search(r"(\d{2,3})\s*days", low)
    if m:
        return int(m.group(1))
    for w, n in _WORD_NUM.items():
        if f"{w} days" in low or f"{w} (" in low:
            return n
    return None


def extract_price(text: str) -> float | None:
    m = re.search(r"(?:usd|\$|inr|₹)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    return float(m.group(1).replace(",", "")) if m else None


class ContractAnalystAgent:
    name = "contract_analyst"

    def __init__(self, llm: LLM | None = None, llm_threshold: float = 0.6):
        self.llm = llm
        self.llm_threshold = llm_threshold

    def analyze(self, text: str) -> tuple[list[Clause], Terms | None]:
        clauses = []
        for i, (heading, body) in enumerate(split_sections(text)):
            ctype, conf = keyword_classify(heading, body)
            if self.llm and conf < self.llm_threshold:
                try:
                    r = self.llm.structured(
                        "You classify contract clauses. Reply with the single best clause type.",
                        f"Heading: {heading}\nClause: {body}",
                        _LLMClauseType,
                    )
                    ctype, conf = r.type, r.confidence
                except LLMError:
                    pass
            clauses.append(Clause(id=f"c{i + 1}", type=ctype, heading=heading, text=body, type_confidence=round(conf, 2)))
        return clauses, self.opening_terms(clauses)

    @staticmethod
    def opening_terms(clauses: list[Clause]) -> Terms | None:
        price = days = None
        for c in clauses:
            if c.type == ClauseType.PRICE and price is None:
                price = extract_price(c.text)
            if c.type == ClauseType.PAYMENT_TERMS and days is None:
                days = extract_payment_days(c.text)
        if price is None:
            return None
        return Terms(price=price, payment_days=days or 30)
