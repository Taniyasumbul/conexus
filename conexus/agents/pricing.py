"""Sales/Pricing Agent (RO3): CRM-grounded pricing plan + concession strategy.

With memory:  anchor just above the estimated WTP of similar customers.
Without (cold start / ablation): anchor at list price - what a prompt-only
agent effectively does - which over-anchors low-WTP segments and
under-anchors high-WTP ones.
"""
from __future__ import annotations

from ..config import PricingPolicyConfig
from ..models import DealContext, PricingPlan, Terms
from .memory import MemoryAgent


class SalesPricingAgent:
    name = "sales_pricing"

    def __init__(self, policy: PricingPolicyConfig, memory: MemoryAgent | None):
        self.p = policy
        self.memory = memory

    def value(self, t: Terms) -> float:
        """Our value of a set of terms: price discounted for payment delay."""
        return t.price * (1 - self.p.cost_of_capital * t.payment_days / 365)

    def plan(self, ctx: DealContext) -> PricingPlan:
        floor = ctx.list_price * (1 - self.p.max_discount)
        wtp_ratio, evidence = (None, ["memory disabled"]) if self.memory is None else self.memory.estimate_wtp_ratio(ctx)
        if wtp_ratio:
            wtp = ctx.list_price * wtp_ratio
            anchor = max(floor, wtp * (1 + self.p.anchor_markup_over_wtp))
            target = max(floor, wtp * 0.97)
            limit = max(floor, wtp * self.p.concession_limit_of_wtp)
        else:
            wtp = None
            anchor, target, limit = ctx.list_price, ctx.list_price * 0.9, floor
        d = self.p.target_payment_days
        return PricingPlan(
            anchor=Terms(price=round(anchor, 2), payment_days=d),
            target=Terms(price=round(target, 2), payment_days=d),
            floor_price=round(floor, 2),
            concession_limit=round(limit, 2),
            max_payment_days=self.p.max_payment_days,
            wtp_estimate=round(wtp, 2) if wtp else None,
            evidence=evidence,
        )

    def next_offer(self, plan: PricingPlan, rnd: int, max_rounds: int, their_last: Terms | None) -> Terms:
        """Time-dependent Boulware concession from anchor toward the concession limit
        (memory-informed); only the final round may go down to the policy floor."""
        f = min(1.0, (rnd / max(1, max_rounds - 1)) ** (1 / self.p.boulware_beta))
        stop = plan.floor_price if rnd >= max_rounds else plan.concession_limit
        price = plan.anchor.price - (plan.anchor.price - stop) * f
        days = round(plan.anchor.payment_days + (plan.max_payment_days - plan.anchor.payment_days) * f)
        if their_last:
            days = max(plan.anchor.payment_days, min(days, their_last.payment_days))
            price = max(price, their_last.price)  # never ask for less than they already offered
        return Terms(price=round(price, 2), payment_days=int(days), term_months=plan.anchor.term_months)

    def acceptable(self, plan: PricingPlan, theirs: Terms, our_next: Terms) -> bool:
        if theirs.price < plan.floor_price or theirs.payment_days > plan.max_payment_days:
            return False
        return self.value(theirs) >= self.value(our_next) * 0.995
