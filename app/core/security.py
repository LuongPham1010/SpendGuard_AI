"""
Security Module: 3-Tier Permission Matrix, PII Masking, and Input Guardrails
Shenzhen International FinTech Competition 2026 - Deliverable 05 & 06 Compliance
"""

import re
import unicodedata
from typing import Dict, Any, Optional, List
from app.config import (
    TIER2_MAX_LIMIT_VND,
    SCAM_CRITICAL_RISK_THRESHOLD,
)


class SecurityGuard:
    """Enterprise-grade FinTech Security and Compliance Matrix"""

    PROMPT_INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?(previous|prior|above|earlier|system)\s+(instructions|rules|prompts|directives)",
        r"(?i)system\s+override",
        r"(?i)bypass\s+(all\s+)?(security|guardrails|tier|permission|approval|checks)",
        r"(?i)disregard\s+(all\s+)?(financial\s+)?(safety|rules|limits|instructions)",
        r"(?i)transfer\s+all\s+(funds|money|balance|savings)\s+to",
        r"(?i)jailbreak",
        r"(?i)you\s+are\s+now\s+(DAN|unfiltered|unrestricted|admin|root)",
        r"(?i)drop\s+table",
        r"(?i)delete\s+from\s+wallets",
        r"(?i)give\s+me\s+root\s+access",
        r"(?i)force\s+tier\s*[12]\s+approval",
        r"(?i)forget\s+(everything|all\s+rules|your\s+instructions)",
        r"(?i)act\s+as\s+if\s+human\s+approval\s+is\s+(granted|true)",
        r"(?i)set\s+human_approved\s*(=|to)\s*true",
    ]

    # Bộ từ khóa ngữ nghĩa phát hiện tấn công biến tướng (tiếng Việt & tiếng Anh lách luật)
    SEMANTIC_INJECTION_RULES = [
        (r"\b(bo qua|quen di|xoa bo|lo di|khong can theo)\b", r"\b(quy tac|huong dan|lenh|gioi han|bao mat|an toan|kiem duyet)\b"),
        (r"\b(chuyen het|rut het|chuyen toan bo|vet sach)\b", r"\b(tien|so du|tai khoan|vi|quy khan cap)\b"),
        (r"\b(tu dong duyet|khong can hoi|bo qua xac nhan|phe duyet luon|mac dinh dong y)\b", r"\b(giao dich|chuyen khoan|tier|han muc)\b"),
        (r"\b(pretend|assume|imagine|simulate)\b", r"\b(no\s+limits|no\s+restrictions|approved\s+by\s+user|admin\s+mode|override)\b"),
        (r"\b(new\s+directive|urgent\s+system\s+update|administrative\s+command|developer\s+mode)\b", r"\b(execute|send|transfer|disable|unlock)\b"),
    ]

    @staticmethod
    def normalize_text(text: str) -> str:
        """Lowercase and strip Vietnamese diacritics so rules match accented and unaccented input."""
        if not text:
            return ""
        nfkd = unicodedata.normalize("NFKD", text)
        stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
        return stripped.replace("đ", "d").replace("Đ", "D").lower()

    @staticmethod
    def scan_injection(text: str) -> List[str]:
        """Return every injection pattern or semantic combination matched in text."""
        if not text:
            return []
        hits: List[str] = []
        for pattern in SecurityGuard.PROMPT_INJECTION_PATTERNS:
            m = re.search(pattern, text)
            if m:
                hits.append(m.group(0))

        norm = SecurityGuard.normalize_text(text)
        for pat_a, pat_b in SecurityGuard.SEMANTIC_INJECTION_RULES:
            ma = re.search(pat_a, norm)
            mb = re.search(pat_b, norm)
            if ma and mb:
                hits.append(f"semantic:{ma.group(0)}+{mb.group(0)}")
        return hits

    @staticmethod
    def evaluate_tier(
        action_type: str,
        amount: float = 0.0,
        risk_score: float = 0.0,
        is_override: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate action against 3-Tier Permission Matrix:
        - Tier 1: Read-only & Information Synthesis (100% Autonomous)
        - Tier 2: Controlled Auto-Execution (Under threshold, safe operations)
        - Tier 3: High-Risk Action (Human-in-the-Loop mandatory)
        """
        if risk_score >= SCAM_CRITICAL_RISK_THRESHOLD:
            return {
                "tier": "Tier 3",
                "level": 3,
                "name": "High-Risk Cognitive Lockdown",
                "requires_human_approval": True,
                "status": "APPROVED" if is_override else "LOCKED_COGNITIVE_QUIZ_REQUIRED",
                "reason": f"Risk score ({risk_score:.1f}/100) exceeds threshold ({SCAM_CRITICAL_RISK_THRESHOLD:.1f}). Transfer blocked.",
            }

        if action_type in ("READ_ONLY", "QUERY", "MONTE_CARLO_SIM", "DEBATE_ANALYSIS", "SUBSCRIPTION_SCAN", "TRANSACTION_AUDIT"):
            return {
                "tier": "Tier 1",
                "level": 1,
                "name": "Read-Only / Information Synthesis",
                "requires_human_approval": False,
                "status": "APPROVED",
                "reason": "Non-state-mutating analytical operation. Executed autonomously without user interruption.",
            }

        if action_type in ("INTERNAL_TRANSFER", "AUTO_SAVINGS_SWEEP", "SUBSCRIPTION_UNSUBSCRIBE_MARK"):
            if amount <= TIER2_MAX_LIMIT_VND:
                return {
                    "tier": "Tier 2",
                    "level": 2,
                    "name": "Controlled Autonomous Execution",
                    "requires_human_approval": False,
                    "status": "APPROVED",
                    "reason": f"Amount ({amount:,.0f} VND) is within safe autonomous threshold (<= {TIER2_MAX_LIMIT_VND:,.0f} VND).",
                }
            else:
                return {
                    "tier": "Tier 3",
                    "level": 3,
                    "name": "High-Value Transaction Tier",
                    "requires_human_approval": True,
                    "status": "APPROVED" if is_override else "PENDING_HUMAN_APPROVAL",
                    "reason": f"Amount ({amount:,.0f} VND) exceeds Tier 2 autonomous threshold (> {TIER2_MAX_LIMIT_VND:,.0f} VND). Human approval required.",
                }

        if action_type in ("EXTERNAL_TRANSFER", "ACCOUNT_DRAIN", "CONFIGURATION_OVERRIDE"):
            return {
                "tier": "Tier 3",
                "level": 3,
                "name": "High-Risk External Operation",
                "requires_human_approval": True,
                "status": "APPROVED" if is_override else "PENDING_HUMAN_APPROVAL",
                "reason": "Outbound execution to external party or sensitive setting mutation requires explicit Human-in-the-Loop authorization.",
            }

        return {
            "tier": "Tier 3",
            "level": 3,
            "name": "Unspecified Operation",
            "requires_human_approval": True,
            "status": "APPROVED" if is_override else "PENDING_HUMAN_APPROVAL",
            "reason": f"Action type '{action_type}' default safe routing.",
        }

    @staticmethod
    def mask_pii(text: str) -> str:
        """
        Mask Personally Identifiable Information (PII):
        - Credit / Debit Card numbers
        - Vietnamese National IDs / CCCD (9 or 12 digits)
        - Bank Account numbers
        - Phone numbers
        - Email addresses
        """
        if not text:
            return ""

        masked = str(text)

        def mask_account(match):
            prefix = match.group(1)
            acc = match.group(2)
            if len(acc) >= 8:
                masked_acc = f"{acc[:3]}****{acc[-3:]}"
                return f"{prefix}{masked_acc}"
            return match.group(0)

        masked = re.sub(r"(?i)\b(stk[:\s]*|s[oố]\s*t[aà]i\s*kho[aả]n[:\s]*|tk[:\s]*|account[:\s]*|acct[:\s]*)([0-9]{8,16})\b", mask_account, masked)

        def mask_card(match):
            raw = re.sub(r"[\s-]", "", match.group(0))
            if len(raw) >= 13:
                return f"{raw[:4]} **** **** {raw[-4:]}"
            return match.group(0)

        masked = re.sub(r"\b(?:\d[ -]*?){13,19}\b", mask_card, masked)

        def mask_id(match):
            digits = match.group(0)
            if digits.endswith("00000"):
                return digits              # a round money amount (120000000 VND), not an ID number
            if len(digits) == 12:
                return f"{digits[:3]}******{digits[-3:]}"
            elif len(digits) == 9:
                return f"{digits[:2]}*****{digits[-2:]}"
            return digits

        # an amount written as a float (120000000.0) is money, not an ID: skip digits followed by a decimal part
        masked = re.sub(r"\b(?:\d{9}|\d{12})\b(?![.,]\d)", mask_id, masked)

        def mask_phone(match):
            phone = match.group(0)
            clean = re.sub(r"[\s\.\-]", "", phone)
            if len(clean) >= 10:
                return f"{clean[:3]}****{clean[-3:]}"
            return phone

        masked = re.sub(r"(?:\+84|0)(?:3|5|7|8|9)\d{8}\b", mask_phone, masked)

        def mask_email(match):
            email = match.group(0)
            parts = email.split("@")
            if len(parts) == 2 and len(parts[0]) > 2:
                user = parts[0]
                masked_user = f"{user[0]}***{user[-1]}"
                return f"{masked_user}@{parts[1]}"
            return email

        masked = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", mask_email, masked)

        return masked

    @staticmethod
    def validate_input_guardrail(text: str) -> Dict[str, Any]:
        """Scan input text for prompt injection, jailbreaks, or hostile control words."""
        if not text:
            return {"safe": True, "detected_pattern": None, "sanitized_text": ""}

        hits = SecurityGuard.scan_injection(text)
        if hits:
            return {
                "safe": False,
                "detected_pattern": hits[0],
                "sanitized_text": "[PROMPT INJECTION BLOCKED BY SPENDGUARD GUARDRAIL]",
                "reason": f"Malicious command pattern detected: '{hits[0]}'",
            }

        sanitized = SecurityGuard.mask_pii(text)
        return {
            "safe": True,
            "detected_pattern": None,
            "sanitized_text": sanitized,
            "reason": "Input passed all adversarial guardrail filters.",
        }


