"""
30-Day Cashflow Forecaster & Liquidity Shortfall Early-Warning Engine
Shenzhen International FinTech Competition 2026 - Topic A: Proactive Financial Intelligence
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.config import TIER2_MAX_LIMIT_VND
from app.models.schemas import Transaction
from app.core.sandbox_wallets import wallet_manager
from app.core.audit_logger import SandboxAuditLogger
from app.modules.ghost_hunter import GhostSubscriptionHunter


class DailyProjection(BaseModel):
    day: int
    date: str
    projected_balance: float
    scheduled_inflow: float = 0.0
    scheduled_outflow: float = 0.0
    events: List[str] = Field(default_factory=list)


class CashflowForecastResult(BaseModel):
    starting_main_balance: float
    ending_main_balance: float
    minimum_projected_balance: float
    shortfall_detected: bool
    shortfall_date: Optional[str] = None
    shortfall_amount: float = 0.0
    daily_burn_rate: float
    upcoming_subscriptions_total: float
    recommended_tier2_action: Optional[Dict[str, Any]] = None
    projections: List[DailyProjection] = Field(default_factory=list)
    summary: str = ""


class CashflowForecaster:
    """Projects 30-day Main Wallet liquidity, detects shortfalls, and proposes Tier 2 buffer actions."""

    @classmethod
    def forecast_30_days(
        cls,
        transactions: List[Transaction],
        days: int = 30,
        liquidity_floor_vnd: float = 5_000_000.0,
    ) -> CashflowForecastResult:
        main_wallet = wallet_manager.get_wallet("main")
        vault_wallet = wallet_manager.get_wallet("emergency")
        starting_balance = main_wallet.balance if main_wallet else 65_000_000.0
        vault_balance = vault_wallet.balance if vault_wallet else 120_000_000.0

        # 1. Calculate historical daily discretionary + essential burn rate (excluding rent & subscriptions)
        outflows = [t for t in transactions if t.type == "outflow" and t.category != "Income"]
        inflows = [t for t in transactions if t.type == "inflow" or t.category == "Income"]

        distinct_months = max(1, len({str(t.date)[:7] for t in transactions if getattr(t, "date", "")}))
        non_sub_outflows = [
            t.amount for t in outflows
            if not t.is_subscription and "thue nha" not in t.description.lower() and "vinhomes" not in t.description.lower()
        ]
        monthly_variable_spend = (sum(non_sub_outflows) / distinct_months) if non_sub_outflows else 12_000_000.0
        daily_burn = round(monthly_variable_spend / 30.0, 0)

        # Estimate recurring rent / housing bill (typically due on day 5 of the month)
        rent_txs = [t.amount for t in outflows if "thue nha" in t.description.lower() or "vinhomes" in t.description.lower() or t.subcategory == "Housing"]
        monthly_rent = (sum(rent_txs) / len(rent_txs)) if rent_txs else 8_500_000.0

        # Estimate monthly salary inflow (typically day 28)
        monthly_salary = (sum(t.amount for t in inflows) / distinct_months) if inflows else 35_000_000.0

        # 2. Active subscriptions and expected billing day-of-month
        subs = GhostSubscriptionHunter.detect_subscriptions(transactions)
        active_subs = [s for s in subs if s.status == "active"]
        subs_by_dom: Dict[int, List[Any]] = {}
        for s in active_subs:
            try:
                dom = int(str(s.last_charged).split("-")[2])
            except Exception:
                dom = 15
            subs_by_dom.setdefault(dom, []).append(s)

        # 3. Step through next 30 days
        today = datetime.now().date()
        balance = starting_balance
        min_balance = balance
        shortfall_detected = False
        shortfall_date: Optional[str] = None
        projections: List[DailyProjection] = []
        upcoming_subs_total = 0.0

        for d_idx in range(1, days + 1):
            cur_date = today + timedelta(days=d_idx)
            dom = cur_date.day
            inflow_day = 0.0
            outflow_day = daily_burn
            events: List[str] = []

            if dom == 5:
                outflow_day += monthly_rent
                events.append(f"Housing / Rent Bill (-{monthly_rent:,.0f} VND)")

            if dom in subs_by_dom:
                for sub in subs_by_dom[dom]:
                    outflow_day += sub.amount
                    upcoming_subs_total += sub.amount
                    events.append(f"Subscription: {sub.merchant} (-{sub.amount:,.0f} VND)")

            if dom == 28:
                inflow_day += monthly_salary
                events.append(f"Projected Salary Inflow (+{monthly_salary:,.0f} VND)")

            balance = round(balance + inflow_day - outflow_day, 0)
            if balance < min_balance:
                min_balance = balance

            if balance < liquidity_floor_vnd and not shortfall_detected:
                shortfall_detected = True
                shortfall_date = cur_date.isoformat()

            projections.append(
                DailyProjection(
                    day=d_idx,
                    date=cur_date.isoformat(),
                    projected_balance=balance,
                    scheduled_inflow=inflow_day,
                    scheduled_outflow=outflow_day,
                    events=events,
                )
            )

        shortfall_amt = max(0.0, round(liquidity_floor_vnd - min_balance, 0))
        recommended_action: Optional[Dict[str, Any]] = None

        if shortfall_detected:
            topup = min(TIER2_MAX_LIMIT_VND, max(1_000_000.0, shortfall_amt))
            recommended_action = {
                "tier": "Tier 2",
                "action": "LIQUIDITY_SHIELD_REPLENISH",
                "source_wallet": "Emergency Vault",
                "destination_wallet": "Main Wallet",
                "suggested_amount_vnd": topup,
                "reason": f"Projected Main Wallet balance drops to {min_balance:,.0f} VND on {shortfall_date} (below {liquidity_floor_vnd:,.0f} VND safety floor).",
            }
        elif balance - starting_balance > 5_000_000.0 and vault_balance >= 0:
            surplus_sweep = min(TIER2_MAX_LIMIT_VND, round((balance - starting_balance) * 0.5, 0))
            recommended_action = {
                "tier": "Tier 2",
                "action": "SURPLUS_AUTO_SWEEP",
                "source_wallet": "Main Wallet",
                "destination_wallet": "Emergency Vault",
                "suggested_amount_vnd": surplus_sweep,
                "reason": f"30-day projection shows healthy surplus (+{balance - starting_balance:,.0f} VND). Safe to sweep {surplus_sweep:,.0f} VND into Emergency Vault.",
            }

        summary = (
            f"30-day forecast: Main Wallet starts at {starting_balance:,.0f} VND, "
            f"minimum projected balance {min_balance:,.0f} VND, ending at {balance:,.0f} VND. "
            + (
                f"WARNING: Liquidity shortfall projected on {shortfall_date}. Recommended Tier 2 buffer transfer: {recommended_action['suggested_amount_vnd']:,.0f} VND."
                if shortfall_detected and recommended_action
                else "No liquidity shortfall detected over the next 30 days."
            )
        )

        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="CashflowForecaster",
            action="FORECAST_30D_LIQUIDITY",
            status="SHORTFALL_WARN" if shortfall_detected else "HEALTHY",
            details={
                "starting_balance": starting_balance,
                "min_projected_balance": min_balance,
                "ending_balance": balance,
                "shortfall_detected": shortfall_detected,
                "shortfall_date": shortfall_date,
            },
        )

        return CashflowForecastResult(
            starting_main_balance=starting_balance,
            ending_main_balance=balance,
            minimum_projected_balance=min_balance,
            shortfall_detected=shortfall_detected,
            shortfall_date=shortfall_date,
            shortfall_amount=shortfall_amt,
            daily_burn_rate=daily_burn,
            upcoming_subscriptions_total=upcoming_subs_total,
            recommended_tier2_action=recommended_action,
            projections=projections,
            summary=summary,
        )
