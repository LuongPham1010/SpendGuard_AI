"""Closed-loop month review: analyse -> propose -> execute Tier 1/2 -> queue Tier 3 -> report."""
from dataclasses import dataclass, field
from typing import Dict, List

from app.agent.tools import scan_past_payments, stress_inputs
from app.agent.types import AgentContext, Plan, PlannedCall
from app.config import PLANNER_MAX_CALLS, TIER2_MAX_LIMIT_VND
from app.core.sandbox_wallets import wallet_manager
from app.models.schemas import MonteCarloRequest
from app.modules.auto_categorizer import AutoCategorizer
from app.modules.ghost_hunter import GhostSubscriptionHunter
from app.modules.monte_carlo import MonteCarloEngine


@dataclass
class MonthProposal:
    budget: dict
    subscriptions: list
    stress: dict
    actions: List[PlannedCall] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    next_month_caps: Dict[str, float] = field(default_factory=dict)


def propose_month_actions(ctx: AgentContext) -> MonthProposal:
    # The review covers the latest month with income; the stress test uses the same inputs as run_stress_test
    budget = AutoCategorizer.analyze_spending_framework(ctx.transactions,
                                                        month=AutoCategorizer.latest_statement_month(ctx.transactions))
    subs = [s.model_dump() for s in GhostSubscriptionHunter.detect_subscriptions(ctx.transactions)]
    inputs = stress_inputs(ctx)
    income = budget["total_income"] or inputs["monthly_income"]
    expenses = inputs["monthly_expenses"]
    vault_balance = inputs["initial_savings"]
    stress = MonteCarloEngine.simulate(MonteCarloRequest(**inputs)).model_dump()
    prop = MonthProposal(budget=budget, subscriptions=subs, stress=stress)

    savings_gap = float(budget.get("suggested_savings_sweep_vnd", 0.0))
    buffer_shortfall = max(0.0, float(stress["recommended_emergency_buffer"]) - vault_balance)
    gap = max(savings_gap, buffer_shortfall)
    main = wallet_manager.get_wallet("main")
    liquidity_floor = max(1_000_000.0, expenses)                               # keep one month of expenses in Main
    gap = min(gap, max(0.0, (main.balance if main else 0.0) - liquidity_floor))
    sweep = min(gap, TIER2_MAX_LIMIT_VND)
    if sweep > 500_000:
        reason = "50/30/20 savings gap" if savings_gap >= buffer_shortfall else "emergency buffer shortfall"
        prop.actions.append(PlannedCall("transfer_internal", {"source": "Main Wallet", "destination": "Emergency Vault",
                                                              "amount": round(sweep, 0), "note": f"Month review: {reason} sweep"}))
        prop.notes.append(f"{reason.capitalize()} {gap:,.0f} VND; sweeping {sweep:,.0f} VND within the Tier 2 limit.")
    facts = getattr(ctx.profile, "facts", {}) if ctx.profile is not None else {}
    unused = [m.strip().lower() for m in (facts.get("unused_subscriptions", "") or "").split(",") if m.strip()]
    for s in subs:
        if s["status"] == "active" and s["merchant"].lower() in unused:
            prop.actions.append(PlannedCall("cancel_subscription", {"merchant": s["merchant"]}))
            prop.notes.append(f"{s['merchant']} marked unused by you; cancelling saves {s['annual_leakage']:,.0f} VND per year.")
    remaining = min(gap - sweep, 3 * TIER2_MAX_LIMIT_VND)                      # a top-up proposal is bounded, not "everything"
    if stress["resilience_score"] < 80 and remaining > 0:
        prop.actions.append(PlannedCall("transfer_internal", {"source": "Main Wallet", "destination": "Emergency Vault",
                                                              "amount": round(remaining, 0),
                                                              "note": "Month review: resilience top-up (needs approval)"}))
        prop.notes.append(f"Resilience {stress['resilience_score']}/100; proposing an extra {remaining:,.0f} VND top-up for your approval.")
    for k in ("Needs", "Wants"):
        b = budget["breakdown"][k]
        if b["status"] == "OVER_BUDGET":
            prop.next_month_caps[k] = round(income * b["target_pct"] / 100.0, 0)
    return prop


def expand_run_my_month(ctx: AgentContext) -> Plan:
    prop = propose_month_actions(ctx)
    past = scan_past_payments(ctx, log=False)          # the scan_past_transactions call below writes the audit entry
    scams = [{"date": s["date"], "amount": s["amount"], "merchant": s["merchant"], "scam_type": s["scam_type"]}
             for s in past["flagged"]]
    # the scan opens the plan and the report closes it, so truncation can only drop proposed actions
    actions = list(prop.actions)[:PLANNER_MAX_CALLS - 2]
    calls = [PlannedCall("scan_past_transactions", {})] + actions
    calls.append(PlannedCall("run_my_month_report", {
        "suspected_scams": scams,
        "sweep_amount": next((c.args["amount"] for c in actions if c.tool == "transfer_internal"), 0.0),
        "cancelled": [c.args["merchant"] for c in actions if c.tool == "cancel_subscription"],
        "resilience_score": prop.stress["resilience_score"],
        "savings_rate_pct": prop.budget["savings_rate_pct"],
        "next_month_caps": prop.next_month_caps,
        "notes": prop.notes,
    }))
    return Plan("run_my_month", calls, "rule")
