"""
Auto-Categorizer Module: 50/30/20 Financial Framework, Multi-Month Trends & Autonomous Rule Engine
Shenzhen International FinTech Competition 2026 - Topic A: Personal Finance Assistant
"""

import json
from typing import List, Dict, Any, Tuple, Optional
from app.config import (
    BUDGET_TARGET_NEEDS_PCT,
    BUDGET_TARGET_WANTS_PCT,
    BUDGET_TARGET_SAVINGS_PCT,
)
from app.models.schemas import Transaction
from app.core.audit_logger import SandboxAuditLogger
from app.core.llm_helper import extract_json_from_text
from app.core.llm_gateway import gateway, Part


class AutoCategorizer:
    """Classifies transactions into 50/30/20 framework and computes single/multi-month budget analytics"""

    _llm_cache: Dict[str, Tuple[str, str]] = {}

    KEYWORDS_NEEDS = [
        "vinhomes", "thue nha", "rent", "tien nha",
        "evn", "tien dien", "dien luc", "electricity",
        "sawaco", "tien nuoc", "water",
        "viettel", "vnpt", "fpt telecom", "internet",
        "winmart", "co.opmart", "bach hoa xanh", "mega market", "groceries", "thuc pham",
        "petrolimex", "xang", "gasoline", "grab car", "be car", "transport",
        "pharmacity", "long chau", "benh vien", "kham benh", "thuoc", "healthcare",
        "bao hiem", "insurance", "bhyt",
    ]

    KEYWORDS_WANTS = [
        "highlands", "starbucks", "phuc long", "the coffee house", "coffee", "cafe",
        "shopee", "lazada", "tiki", "uniqlo", "zara", "h&m", "shopping",
        "cgv", "bap nuoc", "cinema", "entertainment", "steam", "game",
        "haidilao", "kichi kichi", "gogi", "lau", "pub", "bar", "dining",
        "netflix", "spotify", "apple icloud", "california fitness", "gym", "coursera",
        "iphone", "gadgets", "tai nghe",
    ]

    KEYWORDS_SAVINGS = [
        "tiet kiem", "quy khan cap", "emergency vault", "saving", "deposit",
        "chung khoan", "co phieu", "ssi", "vndirect", "invest",
        "tra no", "loan repayment", "tich luy",
    ]

    @classmethod
    def classify_transaction(cls, description: str, current_category: str = "") -> Tuple[str, str]:
        """Classify description into (category, subcategory)"""
        desc_lower = description.lower()

        for kw in cls.KEYWORDS_SAVINGS:
            if kw in desc_lower:
                return "Savings/Debts", "Emergency Vault Deposit"

        for kw in cls.KEYWORDS_NEEDS:
            if kw in desc_lower:
                if any(x in desc_lower for x in ["thue nha", "rent", "vinhomes"]):
                    return "Needs", "Housing"
                if any(x in desc_lower for x in ["evn", "dien", "sawaco", "nuoc", "internet", "viettel", "vnpt"]):
                    return "Needs", "Utilities"
                if any(x in desc_lower for x in ["winmart", "co.op", "bach hoa", "thuc pham"]):
                    return "Needs", "Groceries"
                if any(x in desc_lower for x in ["petrolimex", "xang", "grab car"]):
                    return "Needs", "Transport"
                if any(x in desc_lower for x in ["pharmacity", "thuoc", "benh vien"]):
                    return "Needs", "Healthcare"
                return "Needs", "Essential Expense"

        for kw in cls.KEYWORDS_WANTS:
            if kw in desc_lower:
                if any(x in desc_lower for x in ["coffee", "cafe", "highlands", "starbucks", "phuc long", "haidilao", "an toi"]):
                    return "Wants", "Dining"
                if any(x in desc_lower for x in ["shopee", "lazada", "uniqlo", "zara"]):
                    return "Wants", "Shopping"
                if any(x in desc_lower for x in ["netflix", "spotify", "icloud", "fitness", "gym", "coursera"]):
                    return "Wants", "Subscription"
                if any(x in desc_lower for x in ["cgv", "cinema", "game", "steam"]):
                    return "Wants", "Entertainment"
                if any(x in desc_lower for x in ["iphone", "gadget", "tai nghe"]):
                    return "Wants", "Gadgets"
                return "Wants", "Discretionary"

        # The model only fills gaps: a category already on the statement is kept, so the 50/30/20 figures match offline mode
        if gateway.available and (not current_category or current_category == "General"):
            ai_res = cls.classify_with_gemini(description)
            if ai_res:
                return ai_res

        if current_category in ("Needs", "Wants", "Savings/Debts", "Income"):
            return current_category, "General"
        return "Wants", "General"

    @classmethod
    def classify_with_gemini(cls, description: str, amount: float = 0.0) -> Optional[Tuple[str, str]]:
        """Classify a transaction into the 50/30/20 framework through the gateway (None when offline)."""
        if not gateway.available:
            return None
        if description in cls._llm_cache:            # one model call per description, not one per turn
            return cls._llm_cache[description]
        res = gateway.generate('Classify into {"category": "Needs"|"Wants"|"Savings/Debts"|"Income", "subcategory": str}.',
                               instructions="You classify personal-finance transactions under the 50/30/20 rule.",
                               untrusted=[Part(kind="text", content=f"{description} | {amount} VND", source="transaction")],
                               purpose="categorize")
        parsed = res.data or extract_json_from_text(res.text)
        if res.available and parsed and parsed.get("category") in ("Needs", "Wants", "Savings/Debts", "Income"):
            cls._llm_cache[description] = (parsed["category"], parsed.get("subcategory", "General"))
            return cls._llm_cache[description]
        return None

    @classmethod
    def analyze_spending_framework(
        cls,
        transactions: List[Transaction],
        month: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute total income, expenses, 50/30/20 adherence, and budget health score.
        If `month` (e.g., "2026-08" or "08") is provided, filters transactions to that month.
        """
        filtered_txs = transactions
        if month:
            m_clean = month.strip()
            filtered_txs = [
                t for t in transactions
                if str(getattr(t, "date", "")).startswith(m_clean)
                or (len(m_clean) == 2 and str(getattr(t, "date", ""))[5:7] == m_clean)
            ]

        total_income = 0.0
        total_expense = 0.0
        needs_sum = 0.0
        wants_sum = 0.0
        savings_sum = 0.0

        for tx in filtered_txs:
            if tx.type == "inflow" or tx.category == "Income":
                total_income += tx.amount
            else:
                total_expense += tx.amount
                if tx.category == "Needs":
                    needs_sum += tx.amount
                elif tx.category == "Wants":
                    wants_sum += tx.amount
                elif tx.category == "Savings/Debts":
                    savings_sum += tx.amount
                else:
                    cat, _ = cls.classify_transaction(tx.description, tx.category)
                    if cat == "Needs":
                        needs_sum += tx.amount
                    elif cat == "Wants":
                        wants_sum += tx.amount
                    else:
                        savings_sum += tx.amount

        benchmark_base = total_income if total_income > 0 else total_expense
        if benchmark_base == 0:
            benchmark_base = 1.0

        needs_pct = round((needs_sum / benchmark_base) * 100, 1)
        wants_pct = round((wants_sum / benchmark_base) * 100, 1)
        savings_pct = round((savings_sum / benchmark_base) * 100, 1)

        needs_dev = abs(needs_pct - (BUDGET_TARGET_NEEDS_PCT * 100))
        wants_dev = abs(wants_pct - (BUDGET_TARGET_WANTS_PCT * 100))
        savings_dev = abs(savings_pct - (BUDGET_TARGET_SAVINGS_PCT * 100))
        total_deviation = needs_dev + wants_dev + savings_dev
        adherence_score = max(0.0, min(100.0, round(100.0 - (total_deviation * 0.8), 1)))

        suggested_savings_target = total_income * BUDGET_TARGET_SAVINGS_PCT
        savings_gap = max(0.0, suggested_savings_target - savings_sum)

        result = {
            "month": month or "all",
            "transaction_count": len(filtered_txs),
            "total_income": total_income,
            "total_expense": total_expense,
            "net_surplus": total_income - total_expense,
            "breakdown": {
                "Needs": {
                    "amount": needs_sum,
                    "actual_pct": needs_pct,
                    "target_pct": BUDGET_TARGET_NEEDS_PCT * 100,
                    "status": "HEALTHY" if needs_pct <= 50 else "OVER_BUDGET",
                },
                "Wants": {
                    "amount": wants_sum,
                    "actual_pct": wants_pct,
                    "target_pct": BUDGET_TARGET_WANTS_PCT * 100,
                    "status": "HEALTHY" if wants_pct <= 30 else "OVER_BUDGET",
                },
                "Savings": {
                    "amount": savings_sum,
                    "actual_pct": savings_pct,
                    "target_pct": BUDGET_TARGET_SAVINGS_PCT * 100,
                    "status": "ON_TRACK" if savings_pct >= 20 else "UNDER_FUNDED",
                },
            },
            "adherence_score": adherence_score,
            "savings_rate_pct": savings_pct,
            "suggested_savings_sweep_vnd": savings_gap,
        }

        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="AutoCategorizer",
            action="CALCULATE_50_30_20_FRAMEWORK",
            status="SUCCESS",
            details={
                "month": month or "all",
                "total_income": total_income,
                "total_expense": total_expense,
                "adherence_score": adherence_score,
                "savings_gap": savings_gap,
            },
        )

        return result

    @classmethod
    def latest_statement_month(cls, transactions: List[Transaction]) -> Optional[str]:
        """Most recent YYYY-MM that contains income: the latest month with a full pay cycle, not a trailing stub."""
        income_months = sorted({str(t.date)[:7] for t in transactions
                                if (t.type == "inflow" or t.category == "Income") and len(str(t.date)) >= 7})
        if income_months:
            return income_months[-1]
        months = sorted({str(t.date)[:7] for t in transactions if len(str(getattr(t, "date", ""))) >= 7})
        return months[-1] if months else None

    @classmethod
    def compute_multi_month_trends(cls, transactions: List[Transaction]) -> Dict[str, Any]:
        """Group transactions by YYYY-MM and compute monthly 50/30/20 trends & MoM deltas."""
        months = sorted({str(t.date)[:7] for t in transactions if getattr(t, "date", "") and len(str(t.date)) >= 7})
        series: List[Dict[str, Any]] = []
        for m in months:
            snap = cls.analyze_spending_framework(transactions, month=m)
            series.append({
                "month": m,
                "income": snap["total_income"],
                "expense": snap["total_expense"],
                "needs": snap["breakdown"]["Needs"]["amount"],
                "wants": snap["breakdown"]["Wants"]["amount"],
                "savings": snap["breakdown"]["Savings"]["amount"],
                "savings_rate_pct": snap["savings_rate_pct"],
                "adherence_score": snap["adherence_score"],
            })

        mom_expense_delta_pct = 0.0
        if len(series) >= 2 and series[-2]["expense"] > 0:
            mom_expense_delta_pct = round(
                ((series[-1]["expense"] - series[-2]["expense"]) / series[-2]["expense"]) * 100.0, 1
            )

        return {
            "months": months,
            "series": series,
            "mom_expense_delta_pct": mom_expense_delta_pct,
        }
