"""
Virtual Sandbox Wallets Module with Persistent JSON Storage
Shenzhen International FinTech Competition 2026 - Autonomous Execution Evidence
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from app.config import DATA_DIR
from app.models.schemas import Wallet, WalletTransferRequest, WalletTransferResponse
from app.core.security import SecurityGuard
from app.core.audit_logger import SandboxAuditLogger

WALLETS_PATH = DATA_DIR / "memory" / "wallets.json"


class SandboxWalletManager:
    """Manages virtual wallets with 3-tier safety barriers, atomic state transitions, and JSON persistence."""

    DEFAULT_BALANCES = {
        "main": 65_000_000.0,
        "emergency": 120_000_000.0,
        "fun": 15_000_000.0,
    }

    def __init__(self, storage_path: Path = WALLETS_PATH):
        self.storage_path = Path(storage_path)
        self._wallets: Dict[str, Wallet] = self._default_wallets()
        self._load_persisted()

    @classmethod
    def _default_wallets(cls) -> Dict[str, Wallet]:
        return {
            "main": Wallet(
                id="main",
                name="Main Wallet",
                balance=cls.DEFAULT_BALANCES["main"],
                currency="VND",
                description="Daily checking & primary income inflow account",
                color="blue",
                icon="credit-card",
            ),
            "emergency": Wallet(
                id="emergency",
                name="Emergency Vault",
                balance=cls.DEFAULT_BALANCES["emergency"],
                currency="VND",
                description="Locked 6-month safety buffer & high-yield reserve",
                color="emerald",
                icon="shield-check",
            ),
            "fun": Wallet(
                id="fun",
                name="Fun Wallet",
                balance=cls.DEFAULT_BALANCES["fun"],
                currency="VND",
                description="Discretionary wants, hobbies & entertainment budget",
                color="purple",
                icon="sparkles",
            ),
        }

    def _load_persisted(self) -> None:
        if not self.storage_path.exists():
            self.save()
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, w in self._wallets.items():
                    if k in raw and isinstance(raw[k], (int, float)):
                        w.balance = float(raw[k])
                    elif k in raw and isinstance(raw[k], dict) and "balance" in raw[k]:
                        w.balance = float(raw[k]["balance"])
        except Exception as e:
            print(f"[SandboxWallets] Could not load persisted wallets: {e}")

    def save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {k: w.model_dump() for k, w in self._wallets.items()}
            self.storage_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[SandboxWallets] Could not save wallets: {e}")

    def reset_wallets(self) -> List[Wallet]:
        """Reset all sandbox wallets back to initial benchmark balances and persist."""
        self._wallets = self._default_wallets()
        self.save()
        SandboxAuditLogger.log_event(
            tier="Tier 1",
            module="SandboxWallets",
            action="WALLETS_RESET",
            status="RESET_TO_DEFAULT",
            details={k: w.balance for k, w in self._wallets.items()},
        )
        return self.get_all_wallets()

    def _normalize_wallet_id(self, name_or_id: str) -> Optional[str]:
        target = name_or_id.lower().strip()
        if "main" in target:
            return "main"
        if "emerg" in target or "vault" in target:
            return "emergency"
        if "fun" in target or "play" in target:
            return "fun"
        return None

    def get_all_wallets(self) -> List[Wallet]:
        return list(self._wallets.values())

    def get_wallet(self, name_or_id: str) -> Optional[Wallet]:
        key = self._normalize_wallet_id(name_or_id)
        if key and key in self._wallets:
            return self._wallets[key]
        return None

    def execute_transfer(self, req: WalletTransferRequest) -> WalletTransferResponse:
        trace_id = str(uuid.uuid4())[:8]
        src_key = self._normalize_wallet_id(req.source_wallet)
        dst_key = self._normalize_wallet_id(req.destination_wallet)

        if not src_key or not dst_key:
            SandboxAuditLogger.log_event(
                tier="Tier 2",
                module="SandboxWallets",
                action="INTERNAL_TRANSFER",
                status="FAILED_INVALID_WALLET",
                details={"src": req.source_wallet, "dst": req.destination_wallet, "amount": req.amount},
            )
            return WalletTransferResponse(
                success=False,
                tier="Tier 2",
                status="REJECTED",
                message="Invalid wallet identifier provided.",
                source_wallet=req.source_wallet,
                destination_wallet=req.destination_wallet,
                amount=req.amount,
                trace_id=trace_id,
            )

        if src_key == dst_key:
            return WalletTransferResponse(
                success=False,
                tier="Tier 2",
                status="REJECTED",
                message="Source and destination wallets must be different.",
                source_wallet=req.source_wallet,
                destination_wallet=req.destination_wallet,
                amount=req.amount,
                trace_id=trace_id,
            )

        if req.amount <= 0:
            return WalletTransferResponse(
                success=False,
                tier="Tier 2",
                status="REJECTED",
                message="Transfer amount must be strictly greater than 0.",
                source_wallet=req.source_wallet,
                destination_wallet=req.destination_wallet,
                amount=req.amount,
                trace_id=trace_id,
            )

        src_wallet = self._wallets[src_key]
        dst_wallet = self._wallets[dst_key]

        if src_wallet.balance < req.amount:
            SandboxAuditLogger.log_event(
                tier="Tier 2",
                module="SandboxWallets",
                action="INTERNAL_TRANSFER",
                status="FAILED_INSUFFICIENT_FUNDS",
                details={
                    "src": src_wallet.name,
                    "dst": dst_wallet.name,
                    "amount": req.amount,
                    "current_balance": src_wallet.balance,
                },
            )
            return WalletTransferResponse(
                success=False,
                tier="Tier 2",
                status="REJECTED",
                message=f"Insufficient balance in {src_wallet.name} ({src_wallet.balance:,.0f} VND available).",
                source_wallet=src_wallet.name,
                destination_wallet=dst_wallet.name,
                amount=req.amount,
                new_source_balance=src_wallet.balance,
                new_dest_balance=dst_wallet.balance,
                trace_id=trace_id,
            )

        tier_decision = SecurityGuard.evaluate_tier(
            action_type="INTERNAL_TRANSFER",
            amount=req.amount,
            risk_score=0.0,
            is_override=req.security_override or req.quiz_passed,
        )

        tier_label = tier_decision["tier"]

        if tier_decision["requires_human_approval"] and not (req.security_override or req.quiz_passed):
            SandboxAuditLogger.log_event(
                tier=tier_label,
                module="SandboxWallets",
                action="TRANSFER_HELD_FOR_APPROVAL",
                status="HELD_FOR_APPROVAL",
                details={
                    "src": src_wallet.name,
                    "dst": dst_wallet.name,
                    "amount": req.amount,
                    "reason": tier_decision["reason"],
                },
            )
            return WalletTransferResponse(
                success=False,
                tier=tier_label,
                status="HELD_FOR_APPROVAL",
                message=tier_decision["reason"],
                source_wallet=src_wallet.name,
                destination_wallet=dst_wallet.name,
                amount=req.amount,
                new_source_balance=src_wallet.balance,
                new_dest_balance=dst_wallet.balance,
                trace_id=trace_id,
            )

        # Perform atomic transfer and persist to JSON
        src_wallet.balance -= req.amount
        dst_wallet.balance += req.amount
        self.save()

        status_label = "AUTO_EXECUTED" if tier_label == "Tier 2" else "HUMAN_APPROVED_EXECUTED"
        SandboxAuditLogger.log_event(
            tier=tier_label,
            module="SandboxWallets",
            action="TRANSFER_COMPLETED",
            status=status_label,
            details={
                "src": src_wallet.name,
                "dst": dst_wallet.name,
                "amount": req.amount,
                "note": req.note,
                "new_src_balance": src_wallet.balance,
                "new_dst_balance": dst_wallet.balance,
                "trace_id": trace_id,
                "signature": json.dumps({"source": src_wallet.name, "destination": dst_wallet.name,
                                         "payee_account": None, "amount": float(req.amount)}, sort_keys=True),
            },
        )

        return WalletTransferResponse(
            success=True,
            tier=tier_label,
            status="EXECUTED",
            message=f"Successfully transferred {req.amount:,.0f} VND from {src_wallet.name} to {dst_wallet.name}.",
            source_wallet=src_wallet.name,
            destination_wallet=dst_wallet.name,
            amount=req.amount,
            new_source_balance=src_wallet.balance,
            new_dest_balance=dst_wallet.balance,
            trace_id=trace_id,
        )


# Global singleton instance
wallet_manager = SandboxWalletManager()
