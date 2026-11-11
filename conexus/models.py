"""Shared data model. Every agent reads/writes these types via the NegotiationState."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ClauseType(str, Enum):
    PAYMENT_TERMS = "payment_terms"
    PRICE = "price"
    LIABILITY_CAP = "liability_cap"
    INDEMNIFICATION = "indemnification"
    IP_OWNERSHIP = "ip_ownership"
    CONFIDENTIALITY = "confidentiality"
    TERMINATION = "termination"
    AUTO_RENEWAL = "auto_renewal"
    GOVERNING_LAW = "governing_law"
    WARRANTY = "warranty"
    NON_COMPETE = "non_compete"
    DATA_PROTECTION = "data_protection"
    ASSIGNMENT = "assignment"
    OTHER = "other"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Clause(BaseModel):
    id: str
    type: ClauseType
    heading: str = ""
    text: str
    type_confidence: float = 1.0


class ClauseRisk(BaseModel):
    clause_id: str
    clause_type: ClauseType
    level: RiskLevel
    score: float = Field(ge=0, le=1, description="P(clause requires human review)")
    requires_human: bool
    redlinable: bool = False
    redline: str | None = None
    reasons: list[str] = []
    source: str = "hybrid"


class Terms(BaseModel):
    """Negotiable commercial issues. Price is total annual contract value."""
    price: float
    payment_days: int = 30
    term_months: int = 12


class DealContext(BaseModel):
    customer: str
    segment: Literal["startup", "smb", "mid_market", "enterprise"]
    region: Literal["india", "us", "eu", "apac"]
    product: Literal["core", "pro", "suite"]
    seats: int
    list_price: float  # annual list price for the whole deal


class DealRecord(BaseModel):
    deal_id: str
    segment: str
    region: str
    product: str
    seats: int
    list_price: float
    final_price: float
    payment_days: int
    term_months: int
    won: bool
    rounds: int

    @property
    def price_ratio(self) -> float:
        return self.final_price / self.list_price


class PricingPlan(BaseModel):
    anchor: Terms
    target: Terms
    floor_price: float
    concession_limit: float  # where we stop conceding before the final round
    max_payment_days: int
    wtp_estimate: float | None = None
    evidence: list[str] = []


class Offer(BaseModel):
    round: int
    sender: Literal["us", "them"]
    terms: Terms | None = None
    message: str = ""
    accept: bool = False
    walk_away: bool = False
    redline_responses: dict[str, bool] = {}  # clause_id -> accepted?
    new_legal_terms: bool = False


EscalationKind = Literal["risky_clause", "redline_rejected", "new_legal_terms", "no_deal_high_value", "value_limit", "none"]


class EscalationDecision(BaseModel):
    escalate: bool
    stage: Literal["pre_negotiation", "in_negotiation", "pre_signature", "none"] = "none"
    kind: EscalationKind = "none"
    triggers: list[str] = []
    score: float = 0.0
    clause_ids: list[str] = []


class HumanDecision(BaseModel):
    approve: bool
    reviewer: str = "reviewer"
    note: str = ""


class Outcome(BaseModel):
    status: Literal["agreed", "escalated", "walked_away", "no_agreement", "rejected_by_human", "handed_off"]
    final_terms: Terms | None = None
    rounds: int = 0
    escalation: EscalationDecision | None = None
    signed_unreviewed_risky_clauses: int = 0
    accepted_redlines: list[str] = []
    envelope_id: str | None = None


Status = Literal["analyzed", "awaiting_reply", "awaiting_human", "signed", "closed"]


class NegotiationState(BaseModel):
    """The shared blackboard that all agents coordinate through (RO1).

    It is also the persisted state of the Orchestrator's state machine, so a
    negotiation can pause (waiting for an e-mail reply or a human decision)
    and resume later from the database."""
    contract_id: str
    context: DealContext
    status: Status = "analyzed"
    clauses: list[Clause] = []
    risks: list[ClauseRisk] = []
    opening_terms: Terms | None = None
    plan: PricingPlan | None = None
    similar_deals: list[DealRecord] = []
    history: list[Offer] = []
    pending_redlines: list[str] = []      # all redlines we proposed
    last_sent_redlines: list[str] = []    # redlines still open in the last message
    redline_results: dict[str, bool] = {}
    reviewed_clauses: list[str] = []      # cleared by a human reviewer
    round: int = 0
    their_last: Terms | None = None
    last_our_offer: Terms | None = None
    agreed_terms: Terms | None = None
    escalation: EscalationDecision | None = None
    human_decisions: list[HumanDecision] = []
    outcome: Outcome | None = None
