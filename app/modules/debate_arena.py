"""
Multi-Agent Financial Debate Arena
Facts are computed in Python first; three separate model calls (Optimist, Risk Auditor, Arbiter) each receive the
same facts block and the prior turns and must cite facts by key. A deterministic engine covers offline mode.
"""

import json
from typing import Dict, List, Optional

from app.models.schemas import DebateRequest, DebateResponse, DebateTurn
from app.core.sandbox_wallets import wallet_manager
from app.core.audit_logger import SandboxAuditLogger
from app.core.security import SecurityGuard
from app.core.llm_gateway import gateway, Part
from app.core.llm_helper import extract_json_from_text


class FinancialDebateArena:
    """Orchestrates a three-agent debate for high-stake purchases against live sandbox balances"""

    @classmethod
    def run_debate(cls, request: DebateRequest) -> DebateResponse:
        guardrail = SecurityGuard.validate_input_guardrail(f"{request.item_name} {request.user_justification}")
        if not guardrail["safe"]:
            return DebateResponse(
                item_name=request.item_name,
                price=request.price,
                verdict="DENIED",
                confidence_score=99.0,
                executive_summary="Security guardrail triggered: hostile or manipulative input pattern detected in purchase request.",
                turns=[
                    DebateTurn(
                        agent="Arbiter (Security Protocol)",
                        avatar="shield",
                        stance="VERDICT",
                        message=f"Request rejected due to policy violation: {guardrail['reason']}",
                        arguments=["Adversarial prompt injection attempt prevented"],
                    )
                ],
                action_plan=["Re-submit the request with a legitimate purchase justification"],
            )

        wallets = wallet_manager.get_all_wallets()
        main_bal = next((w.balance for w in wallets if w.id == "main"), 65_000_000.0)
        vault_bal = next((w.balance for w in wallets if w.id == "emergency"), 120_000_000.0)
        fun_bal = next((w.balance for w in wallets if w.id == "fun"), 15_000_000.0)

        facts = cls.compute_facts(request, main_bal, vault_bal, fun_bal)
        response = cls._run_gateway_debate(request, facts)
        if response:
            SandboxAuditLogger.log_event(tier="Tier 1", module="DebateArena", action="MULTI_AGENT_DEBATE_GATEWAY",
                                         status="SUCCESS", details={"item": request.item_name, "verdict": response.verdict})
            return response

        response = cls._run_simulated_debate(request, main_bal, vault_bal, fun_bal)
        SandboxAuditLogger.log_event(tier="Tier 1", module="DebateArena", action="MULTI_AGENT_DEBATE_ENGINE",
                                     status="SUCCESS", details={"fallback": True, "item": request.item_name, "verdict": response.verdict})
        return response

    @staticmethod
    def compute_facts(req: DebateRequest, main_bal: float, vault_bal: float, fun_bal: float) -> Dict[str, float]:
        income = float(req.user_income or 35_000_000.0)
        return {"price": float(req.price), "income": income,
                "pct_of_income": round(float(req.price) / income * 100.0, 1),
                "five_year_opportunity_cost": round(float(req.price) * (1.08 ** 5), 0),
                "fun_balance": fun_bal, "vault_balance": vault_bal, "main_balance": main_bal,
                "runway_months": round((main_bal + vault_bal) / max(income * 0.65, 1.0), 1)}

    @classmethod
    def _run_gateway_debate(cls, req: DebateRequest, facts: Dict[str, float]) -> Optional[DebateResponse]:
        if not gateway.available:
            return None
        facts_part = Part(kind="text", content=json.dumps(facts), source="facts", trusted=True)
        personas = [("Optimist (Desire Advocate)", "sparkles", "SUPPORT", "debate_optimist",
                     "Argue for the purchase: utility, wellbeing, productivity. Cite facts by key."),
                    ("Risk Auditor (Cold Reality)", "alert-triangle", "OPPOSE", "debate_risk",
                     "Argue against: liquidity, opportunity cost, runway. Cite facts by key."),
                    ("Arbiter (Executive Decision)", "scale", "VERDICT", "debate_arbiter",
                     "Weigh both sides and return verdict APPROVED|DENIED|DELAYED|CONDITIONAL_APPROVAL with conditions.")]
        turns: List[DebateTurn] = []
        verdict, confidence, summary, plan = "DELAYED", 70.0, "", []
        for agent, avatar, stance, purpose, instr in personas:
            prior = "\n".join(f"{t.agent}: {t.message}" for t in turns)
            res = gateway.generate(
                f'Item "{req.item_name}". User justification: "{req.user_justification}". Prior turns:\n{prior}\n'
                'Return JSON {"message": str, "arguments": [str], "verdict": str, "confidence": number, "summary": str, "action_plan": [str]}.',
                instructions=f"You are {agent}. {instr}", untrusted=[facts_part], purpose=purpose)
            data = res.data or extract_json_from_text(res.text) or {}
            msg = str(data.get("message", "")).strip()
            args = [str(a) for a in data.get("arguments", [])]
            cites = any(k in (msg + " ".join(args)) for k in facts)
            if not msg or not cites:
                return None
            turns.append(DebateTurn(agent=agent, avatar=avatar, stance=stance, message=msg, arguments=args))
            if stance == "VERDICT":
                verdict = data.get("verdict", verdict)
                confidence = float(data.get("confidence", confidence))
                summary = str(data.get("summary", ""))
                plan = [str(p) for p in data.get("action_plan", [])]
        return DebateResponse(item_name=req.item_name, price=req.price, verdict=verdict, confidence_score=confidence,
                              executive_summary=summary, turns=turns, action_plan=plan)

    @classmethod
    def _run_simulated_debate(cls, req: DebateRequest, main_bal: float, vault_bal: float, fun_bal: float) -> DebateResponse:
        """Deterministic financial logic mimicking multi-agent trade-offs"""
        price = req.price
        income = req.user_income or 35_000_000.0

        pct_of_income = (price / income) * 100
        five_year_opp_cost = price * ((1 + 0.08) ** 5)
        months_of_fun_wallet = price / (fun_bal if fun_bal > 0 else 1.0)

        if price <= fun_bal:
            verdict = "APPROVED"
            confidence = 94.0
            summary = f"The purchase of {req.item_name} ({price:,.0f} VND) is within your discretionary Fun Wallet balance ({fun_bal:,.0f} VND) with no impact on essential reserves."
            opt_msg = f"Go for it. {req.item_name} delivers immediate personal value. You preserved your Fun Wallet for exactly this kind of reward."
            risk_msg = f"From a strict accounting standpoint, this takes {months_of_fun_wallet*100:.0f}% of your Fun Wallet. Your Emergency Vault ({vault_bal:,.0f} VND) remains untouched. Acceptable risk."
            arb_msg = f"Approved unconditionally. Deduct {price:,.0f} VND from Fun Wallet. Do not draw funds from Main Wallet or Emergency Vault."
            plan = [f"Debit {price:,.0f} VND from Fun Wallet", "Maintain the automatic savings rate for this month"]
        elif price <= fun_bal * 1.5 and pct_of_income <= 50.0:
            verdict = "CONDITIONAL_APPROVAL"
            confidence = 88.0
            summary = f"{req.item_name} represents {pct_of_income:.1f}% of your monthly income. It is feasible under budget reallocation and a 14-day cooling check."
            opt_msg = f"Investing in {req.item_name} could improve efficiency and satisfaction. Delaying indefinitely has its own cost."
            risk_msg = f"At {price:,.0f} VND this is {pct_of_income:.1f}% of your monthly income. Invested at 8% a year it would grow to {five_year_opp_cost:,.0f} VND in 5 years."
            arb_msg = f"Conditional approval: finance 50% from Fun Wallet ({fun_bal:,.0f} VND available) and reallocate discretionary dining and entertainment over the next 60 days."
            plan = [f"Allocate the current Fun Wallet balance ({fun_bal:,.0f} VND) towards the target",
                    "Apply the 14-day anti-impulse rule before checkout", "Verify no emergency expenses occur this month"]
        else:
            verdict = "DENIED"
            confidence = 96.0
            summary = f"Purchase rejected. At {price:,.0f} VND ({pct_of_income:.1f}% of monthly income) this compromises your liquidity and violates Tier 2 safety guidelines."
            opt_msg = f"While {req.item_name} looks attractive, financial distress would cost more than the pleasure of ownership."
            risk_msg = f"This would drain {months_of_fun_wallet:.1f}x your Fun Wallet and threaten core liquidity. The 5-year opportunity loss exceeds {five_year_opp_cost:,.0f} VND."
            arb_msg = f"Purchase DENIED. Do not liquidate the Emergency Vault ({vault_bal:,.0f} VND) for lifestyle inflation. Establish a sinking fund first."
            plan = [f"Set up a monthly sinking fund of {price / 6:,.0f} VND for 6 months",
                    "Look for certified refurbished or second-hand alternatives",
                    "Review feasibility after 6 months of baseline emergency reserves"]

        turns = [
            DebateTurn(agent="Optimist (Desire Advocate)", avatar="sparkles", stance="SUPPORT", message=opt_msg,
                       arguments=[f"Utility and morale from acquiring {req.item_name}", "Recognizes the user's effort and aspiration"]),
            DebateTurn(agent="Risk Auditor (Cold Reality)", avatar="alert-triangle",
                       stance="OPPOSE" if verdict != "APPROVED" else "COMPROMISE", message=risk_msg,
                       arguments=[f"5-year compound opportunity cost: {five_year_opp_cost:,.0f} VND (8% annual return)",
                                  f"Accounts for {pct_of_income:.1f}% of current monthly income"]),
            DebateTurn(agent="Arbiter (Executive Decision)", avatar="scale", stance="VERDICT", message=arb_msg,
                       arguments=[f"Binding verdict: {verdict}", f"Decision confidence: {confidence}%"]),
        ]

        return DebateResponse(item_name=req.item_name, price=price, verdict=verdict, confidence_score=confidence,
                              executive_summary=summary, turns=turns, action_plan=plan)
