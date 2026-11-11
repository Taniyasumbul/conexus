"""Central configuration. Policy knobs live here so they are tunable and logged."""
from __future__ import annotations

import os
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RUNS = ROOT / "runs"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v and k not in os.environ:
            os.environ[k] = v


_load_dotenv()


class EscalationPolicyConfig(BaseModel):
    """When must a human step in? Every field is editable by an Admin on the Settings page;
    each change is written to the audit chain."""
    clause_threshold: float = Field(0.5, ge=0.05, le=0.95, description="Risk score at or above which a clause needs a human")
    combine: Literal["max", "weighted"] = Field("max", description="max: either rules or ML can escalate. weighted: average of both")
    ml_weight: float = Field(0.5, ge=0, le=1, description="ML share of the score when combine = weighted")
    max_rounds: int = Field(8, ge=2, le=20, description="Rounds before the agents stop negotiating")
    autonomy_value_limit: float = Field(250_000.0, ge=0, description="Agreed deals above this annual value need human sign-off")
    escalate_on_new_legal_terms: bool = Field(True, description="Pause when the customer adds new legal obligations")
    escalate_on_rejected_redline: bool = Field(True, description="Pause when a redline on a risk-critical clause is rejected")
    escalate_failed_high_value: float = Field(100_000.0, ge=0, description="Hand failed negotiations above this list price to a person")


class PricingPolicyConfig(BaseModel):
    """How the Sales/Pricing agent negotiates."""
    max_discount: float = Field(0.45, ge=0, le=0.9, description="Deepest discount off list price (sets the price floor)")
    target_payment_days: int = Field(30, ge=0, le=180, description="Payment terms the agents open with")
    max_payment_days: int = Field(60, ge=0, le=180, description="Longest payment terms the agents may concede")
    cost_of_capital: float = Field(0.12, ge=0, le=0.5, description="Annual rate used to value later payment")
    boulware_beta: float = Field(0.5, ge=0.1, le=5, description="Below 1 concedes slowly early; above 1 concedes fast")
    anchor_markup_over_wtp: float = Field(0.10, ge=0, le=1, description="Opening ask above the buyer budget estimated from memory")
    concession_limit_of_wtp: float = Field(0.85, ge=0.5, le=1, description="With memory, do not go below this share of the budget estimate until the last round")
    memory_k: int = Field(25, ge=5, le=200, description="Similar past deals the Memory agent retrieves")

    @model_validator(mode="after")
    def _days(self):
        if self.max_payment_days < self.target_payment_days:
            raise ValueError("max_payment_days must be at least target_payment_days")
        return self


class Settings(BaseModel):
    llm_provider: str = os.getenv("CONEXUS_LLM", "offline")
    anthropic_model: str = os.getenv("CONEXUS_ANTHROPIC_MODEL", "claude-opus-5-5")
    effort: str = os.getenv("CONEXUS_EFFORT", "low")
    ollama_model: str = os.getenv("CONEXUS_OLLAMA_MODEL", "llama3.1:8b")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    escalation: EscalationPolicyConfig = EscalationPolicyConfig()
    pricing: PricingPolicyConfig = PricingPolicyConfig()
    home_jurisdictions: list[str] = ["india", "delhi", "uttar pradesh", "new delhi"]
    crm_path: Path = DATA / "crm" / "deals.csv"
    clause_labels_path: Path = DATA / "labels" / "clauses.jsonl"


def get_settings(**overrides) -> Settings:
    s = Settings()
    return s.model_copy(update=overrides) if overrides else s
