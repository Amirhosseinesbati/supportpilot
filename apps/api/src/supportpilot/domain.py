from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReturnDecision:
    eligible: bool
    requires_review: bool
    code: str
    explanation: str


def assess_return(*, delivered_on: date | None, requested_on: date, category: str,
                  condition: str, ordered_quantity: int, already_returned: int,
                  requested_quantity: int, late_delivery_days: int = 0,
                  policy: dict | None = None) -> ReturnDecision:
    """Northstar's deterministic pilot policy; no model decides eligibility."""
    if requested_quantity < 1 or requested_quantity > ordered_quantity - already_returned:
        return ReturnDecision(False, False, "invalid_quantity", "Requested quantity exceeds the remaining items.")
    if delivered_on is None:
        return ReturnDecision(False, True, "not_delivered", "Delivery has not been confirmed; an operator must investigate.")
    age = (requested_on - delivered_on).days
    if age < 0:
        return ReturnDecision(False, True, "future_delivery", "Delivery date is inconsistent; an operator must investigate.")
    if category in {"custom", "digital"}:
        return ReturnDecision(False, False, "final_sale", "This category is excluded from standard returns.")
    if condition == "damaged":
        return ReturnDecision(True, True, "damage_review", "Damage claims need an operator to inspect the evidence.")
    limits = policy or {}
    standard_days = int(limits.get("standard_days", 30))
    monitor_days = int(limits.get("monitor_days", 21))
    grace_days = int(limits.get("late_delivery_grace_days", 45))
    late_threshold = int(limits.get("late_threshold_days", 7))
    window = monitor_days if category == "monitor" else standard_days
    if age > window:
        if category == "monitor" and late_delivery_days >= late_threshold and age <= grace_days:
            return ReturnDecision(True, True, "late_delivery_exception",
                                  "Monitor arrived late; an operator may approve an exception.")
        return ReturnDecision(False, False, "outside_window", "The applicable return window has passed.")
    if condition not in {"unopened", "opened", "damaged"}:
        return ReturnDecision(False, True, "unknown_condition", "Item condition needs clarification.")
    if condition == "opened":
        return ReturnDecision(True, True, "opened_equipment", "Opened large equipment needs an operator review.")
    return ReturnDecision(True, False, "standard", "Eligible under the standard return policy.")
