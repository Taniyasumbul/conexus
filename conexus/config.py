"""Central configuration. Policy knobs live here so they are tunable and logged."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

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
    # clause-level: hybrid score threshold above which a clause needs a human
    clause_threshold: float = 0.5
    # weight of ML probability vs rule score in the hybrid score
    ml_weight: float = 0.5
    # trajectory-level triggers
    max_rounds: int = 8
    autonomy_value_limit: float = 250_000.0  # deals above this need human sign-off
    escalate_on_new_legal_terms: bool = True
    escalate_on_rejected_redline: bool = True
    # if negotiation fails on a high-value deal, hand to a human rather than walk away
    escalate_failed_high_value: float = 100_000.0


class PricingPolicyConfig(BaseModel):
    max_discount: float = 0.45  # floor = list * (1 - max_discount)
    target_payment_days: int = 30
    max_payment_days: int = 60
    cost_of_capital: float = 0.12  # annual, used to value payment-day concessions
    boulware_beta: float = 0.5  # <1 = concede slowly early (Boulware), >1 = conceder
    anchor_markup_over_wtp: float = 0.10
    concession_limit_of_wtp: float = 0.85  # with memory: don't concede below 85% of estimated WTP until the last round
    memory_k: int = 25


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
