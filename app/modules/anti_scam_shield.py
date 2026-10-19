"""
Cognitive Anti-Scam Shield Module
Shenzhen International FinTech Competition 2026 - Security & Compliance Framework (30% Scoring Rubric)
Detects urgency manipulation, psychological coercion, and Ponzi return promises (> 1%/day).
Enforces Tier 3 lockdown, 60-minute cooling-off reflection timer, and cognitive safety quiz.
"""

import re
from typing import Dict, Any, List
from app.config import (
    SCAM_CRITICAL_RISK_THRESHOLD,
    SCAM_COOLING_OFF_MINUTES,
    PONZI_DAILY_YIELD_THRESHOLD_PCT,
)
from app.models.schemas import AntiScamScanRequest, AntiScamScanResponse, QuizQuestion
from app.core.audit_logger import SandboxAuditLogger
from app.core.security import SecurityGuard


class AntiScamShield:
    """Interception barrier stopping cognitive fraud and social engineering transfers"""

    URGENCY_KEYWORDS = [
        "khan cap", "ngay bay gio", "trong 15 phut", "trong 30 phut", "gap lam", "ngay lap tuc",
        "co hoi duy nhat", "bi mat", "dung noi voi ai", "suat cuoi cung", "gio vang",
        "tai khoan bi khoa", "cong an", "vien kiem sat", "dieu tra", "lenh bat",
        "chuyen tien vao tai khoan an toan", "xac minh danh tinh", "thanh tra",
        "urgent", "act now", "immediate", "within 15 minutes", "police order", "secret",
    ]

    PONZI_KEYWORDS = [
        "lai ngay", "cam ket lai", "loi nhuan khung", "x2 tai khoan", "bao hiem von",
        "robot ai trade", "telegram vip", "chuyen gia doc lenh", "rut tien ngay",
        "guaranteed return", "daily yield", "passive income 100%", "crypto mining",
    ]

    COGNITIVE_QUIZ: List[QuizQuestion] = [
        QuizQuestion(
            id=1,
            question="Has anyone claimed to be a police officer, prosecutor, or bank official demanding you transfer funds immediately to a 'safe account' for an ongoing investigation?",
            options=[
                "Yes, they warned my account is frozen and I must transfer to verify innocence.",
                "No, this transfer is to a verified acquaintance or authorized merchant.",
                "Yes, they contacted me via Telegram/Zalo with legal court badges.",
            ],
            correct_option_index=1,
            explanation="Law enforcement agencies and banks NEVER instruct citizens to transfer money into personal accounts via phone or chat apps.",
        ),
        QuizQuestion(
            id=2,
            question="Is this transfer tied to an investment promising guaranteed returns exceeding 1% per day (over 3,600% APY)?",
            options=[
                "Yes, the Telegram group admin showed screenshots of 2.5% daily profits.",
                "Yes, an AI trading bot guarantees zero risk and instant withdrawals.",
                "No, I recognize that guaranteed returns > 1%/day are mathematically impossible and indicate a Ponzi scheme.",
            ],
            correct_option_index=2,
            explanation="Warren Buffett achieves ~20% per YEAR. A return of 1% per DAY compounds to 3,678% per year—an unmistakable signature of a Ponzi collapse.",
        ),
        QuizQuestion(
            id=3,
            question="Did you independently initiate this payment yourself, without anyone pressuring you with a countdown timer or threats of legal trouble?",
            options=[
                "No, I was told I only have 15 minutes left before my assets are permanently confiscated.",
                "Yes, I independently verified all beneficiary bank details through official channels.",
                "No, an online friend I met last week is guiding me step-by-step.",
            ],
            correct_option_index=1,
            explanation="Scammers systematically weaponize artificial time scarcity to shut down your prefrontal cortex reasoning.",
        ),
    ]

    @classmethod
    def scan_transfer_intent(cls, req: AntiScamScanRequest) -> AntiScamScanResponse:
        # Step 1: Input Guardrail Check
        combined_text = f"{req.transfer_note} {req.source_context} {req.recipient_name}"
        guardrail = SecurityGuard.validate_input_guardrail(combined_text)

        risk_score = 0.0
        manipulation_tactics: List[str] = []
        urgency_detected = False
        ponzi_math_flag = False

        text_lower = combined_text.lower()

        # Step 2: NLP Urgency & Authority Coercion Detection
        matched_urgency = [k for k in cls.URGENCY_KEYWORDS if k in text_lower]
        if matched_urgency:
            urgency_detected = True
            risk_score += 40.0
            manipulation_tactics.append(f"Urgency / Fear Triggers Detected: {', '.join(matched_urgency[:3])}")

        # Step 3: Ponzi Scheme & Investment NLP Patterns
        matched_ponzi_kw = [k for k in cls.PONZI_KEYWORDS if k in text_lower]
        if matched_ponzi_kw:
            risk_score += 35.0
            manipulation_tactics.append(f"High-Yield Investment / Telegram Scam Keywords: {', '.join(matched_ponzi_kw[:3])}")

        # Step 4: Mathematical Reality Check (Compounded Yield Calculation)
        daily_yield = float(req.advertised_yield_daily_pct or 0.0)
        # Check if daily yield mentioned in text if not explicitly set
        if daily_yield <= 0:
            yield_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:ngay|day|hang ngay|moi ngay|mỗi ngày|\/day)", text_lower)
            if yield_match:
                try:
                    daily_yield = float(yield_match.group(1))
                except Exception:
                    daily_yield = 0.0

        if daily_yield >= PONZI_DAILY_YIELD_THRESHOLD_PCT:
            ponzi_math_flag = True
            annual_apy = ((1.0 + (daily_yield / 100.0)) ** 365 - 1.0) * 100.0
            risk_score += 45.0
            manipulation_tactics.append(
                f"Mathematical Impossibility: Advertised {daily_yield}% daily yield compounds to {annual_apy:,.0f}% APY (Standard Ponzi signature)."
            )

        # Step 5: High Amount Flag
        if req.amount >= 20_000_000.0:
            risk_score += 15.0

        # Cap risk score
        risk_score = round(min(100.0, max(5.0, risk_score)), 1)

        # Classify Level
        if risk_score >= SCAM_CRITICAL_RISK_THRESHOLD:
            risk_level = "CRITICAL"
            is_locked = True
            tier = "Tier 3"
            explanation = (
                f"CRITICAL RED ALERT: High probability of financial scam ({risk_score}/100). "
                f"Automated Tier 3 Lockdown enforced. All funds are frozen for {SCAM_COOLING_OFF_MINUTES} minutes. "
                "You must pass the 3-question Cognitive Safety Quiz to disrupt psychological manipulation."
            )
        elif risk_score >= 50.0:
            risk_level = "HIGH"
            is_locked = False
            tier = "Tier 3"
            explanation = (
                f"HIGH RISK DETECTED ({risk_score}/100): Suspicious transfer characteristics detected. "
                "Secondary human authentication and destination account verification strongly recommended."
            )
        elif risk_score >= 25.0:
            risk_level = "MEDIUM"
            is_locked = False
            tier = "Tier 2"
            explanation = f"MODERATE RISK ({risk_score}/100): Standard caution advised. Please confirm beneficiary identity."
        else:
            risk_level = "LOW"
            is_locked = False
            tier = "Tier 2"
            explanation = "LOW RISK: No active scam heuristics or urgency manipulations detected."

        response = AntiScamScanResponse(
            risk_score=risk_score,
            risk_level=risk_level,
            is_locked=is_locked,
            urgency_detected=urgency_detected,
            manipulation_tactics=manipulation_tactics,
            ponzi_math_flag=ponzi_math_flag,
            cooling_off_minutes=SCAM_COOLING_OFF_MINUTES if is_locked else 0,
            cognitive_quiz=cls.COGNITIVE_QUIZ if is_locked else [],
            explanation=explanation,
            tier=tier,
        )

        # Audit Log Event
        status_label = "LOCKDOWN_ENFORCED" if is_locked else ("FLAGGED_HIGH" if risk_score >= 50 else "PASS")
        SandboxAuditLogger.log_event(
            tier=tier,
            module="AntiScamShield",
            action="COGNITIVE_FRAUD_SCAN",
            status=status_label,
            details={
                "risk_score": risk_score,
                "risk_level": risk_level,
                "is_locked": is_locked,
                "recipient": SecurityGuard.mask_pii(req.recipient_account),
                "tactics_count": len(manipulation_tactics),
            },
        )

        return response
