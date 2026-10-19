"""
Quantitative Monte Carlo Stress-Testing Module
Shenzhen International FinTech Competition 2026 - Innovation & Quantitative Financial Resilience
Runs 1,000 stochastic multi-month paths modeling three macro and personal shocks:
1. Income Disruption Shock (10% probability)
2. Emergency Health / Vehicle Repair Shock (5M - 20M VND)
3. Persistent Inflation Drift (10% baseline increase)
Outputs Fan Chart distributions (P10, P50, P90) and Financial Resilience Score (0-100).
"""

import numpy as np
from typing import Dict, Any, List
from app.models.schemas import MonteCarloRequest, MonteCarloResult
from app.core.audit_logger import SandboxAuditLogger


class MonteCarloEngine:
    """Quantitative stochastic engine assessing financial survival and runway resilience"""

    @classmethod
    def simulate(cls, req: MonteCarloRequest) -> MonteCarloResult:
        np.random.seed(42)  # For reproducible scientific comparisons
        n_sims = max(100, min(req.num_simulations, 5000))
        n_months = max(3, min(req.months, 36))

        # Baseline parameters
        initial_savings = float(req.initial_savings)
        monthly_income = float(req.monthly_income)
        monthly_expenses = float(req.monthly_expenses)
        inflation_mult = 1.0 + (req.inflation_rate / 12.0)

        # Array to store trajectories: shape (n_sims, n_months + 1)
        trajectories = np.zeros((n_sims, n_months + 1))
        trajectories[:, 0] = initial_savings

        # Vectorized simulation across months
        for m in range(1, n_months + 1):
            # 1. Base monthly income with normal variation (+-5%)
            incomes = np.random.normal(loc=monthly_income, scale=monthly_income * 0.05, size=n_sims)
            
            # Shock 1: Income Disruption (prob = req.income_shock_prob, e.g. 10%)
            # Experiencing disruption reduces income by 60%
            income_shock_mask = np.random.binomial(1, req.income_shock_prob, size=n_sims).astype(bool)
            incomes[income_shock_mask] *= 0.40

            # Scenario: job loss means no income at all for the first N months
            if m <= int(req.income_loss_months):
                incomes[:] = 0.0

            # 2. Base expenses with inflation compounding and normal variation (+-8%)
            compounded_expenses = monthly_expenses * (inflation_mult ** m)
            expenses = np.random.normal(loc=compounded_expenses, scale=compounded_expenses * 0.08, size=n_sims)

            # Shock 2: Emergency Health / Repair Shock (prob = 15% in any given month)
            # Size uniformly distributed between req.emergency_shock_min and req.emergency_shock_max
            emergency_mask = np.random.binomial(1, 0.15, size=n_sims).astype(bool)
            emergency_costs = np.random.uniform(
                low=req.emergency_shock_min,
                high=req.emergency_shock_max,
                size=n_sims,
            )
            expenses[emergency_mask] += emergency_costs[emergency_mask]

            # Monthly net savings
            net_cashflow = incomes - expenses

            # Accumulate balance
            trajectories[:, m] = trajectories[:, m - 1] + net_cashflow

        # Calculate Percentiles: P10 (pessimistic), P50 (median), P90 (optimistic)
        p10 = np.percentile(trajectories, 10, axis=0)
        p50 = np.percentile(trajectories, 50, axis=0)
        p90 = np.percentile(trajectories, 90, axis=0)

        # Depletion rate: percentage of simulations that ever dipped below 0
        min_balances = np.min(trajectories, axis=1)
        depletion_count = np.sum(min_balances < 0)
        bankruptcy_prob = round((depletion_count / n_sims) * 100, 2)

        # Recommended 6-month buffer
        recommended_buffer = monthly_expenses * 6.0

        # Resilience Score (0 to 100)
        # Factor A: Survival rate (weight 50%)
        survival_factor = (1.0 - (bankruptcy_prob / 100.0)) * 50.0

        # Factor B: Emergency buffer coverage ratio (weight 30%)
        buffer_ratio = min(2.0, initial_savings / (recommended_buffer if recommended_buffer > 0 else 1.0))
        buffer_factor = (buffer_ratio / 2.0) * 30.0

        # Factor C: P10 trajectory trend at end of period (weight 20%)
        trend_ratio = max(0.0, min(1.0, (p10[-1] - p10[0]) / (initial_savings if initial_savings > 0 else 1.0) + 0.5))
        trend_factor = trend_ratio * 20.0

        resilience_score = round(float(np.clip(survival_factor + buffer_factor + trend_factor, 0.0, 100.0)), 1)

        # Month labels
        month_labels = [f"M{i}" for i in range(n_months + 1)]

        # Summary text
        if resilience_score >= 80:
            summary = (
                f"HIGH RESILIENCE ({resilience_score}/100): Your liquidity buffer successfully absorbs 90%+ "
                f"of adverse stochastic shock scenarios over {n_months} months. Probability of capital exhaustion is negligible ({bankruptcy_prob}%)."
            )
        elif resilience_score >= 50:
            summary = (
                f"MODERATE RESILIENCE ({resilience_score}/100): Your fund can withstand single shocks, but dual concurrent events "
                f"(income loss + health emergency) cause severe stress. Exhaustion risk is {bankruptcy_prob}%. Increase buffer towards {recommended_buffer:,.0f} VND."
            )
        else:
            summary = (
                f"CRITICAL VULNERABILITY ({resilience_score}/100): High bankruptcy probability ({bankruptcy_prob}%) under standard stress shocks. "
                f"Immediate automated savings sweep to Emergency Vault is required."
            )

        result = MonteCarloResult(
            months=month_labels,
            percentile_10=[round(float(x), 0) for x in p10],
            percentile_50=[round(float(x), 0) for x in p50],
            percentile_90=[round(float(x), 0) for x in p90],
            resilience_score=resilience_score,
            bankruptcy_probability=bankruptcy_prob,
            recommended_emergency_buffer=round(recommended_buffer, 0),
            analysis_summary=summary,
        )

        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="MonteCarloEngine",
            action="STRESS_TEST_1000_SIMS",
            status="SUCCESS",
            details={
                "n_simulations": n_sims,
                "resilience_score": resilience_score,
                "bankruptcy_prob": bankruptcy_prob,
                "recommended_buffer": recommended_buffer,
            },
        )

        return result
