"""Security validator run before any execution: tier, dry-run, Guardian gate, duplicates, caps, injection downgrade."""
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.agent.tools import ToolRegistry
from app.agent.types import AgentContext, PlannedCall, PreflightDecision
from app.config import TIER2_DAILY_CAP_VND
from app.core.audit_logger import SandboxAuditLogger
from app.core.sandbox_wallets import wallet_manager
from app.modules.guardian import Guardian, TransferIntent, Evidence

MONEY_TOOLS = {"transfer_internal", "transfer_external"}


def transfer_signature(tool: str, args: dict) -> str:
    """Canonical signature shared with the audit log so duplicates can be detected."""
    if tool == "transfer_internal":
        src = wallet_manager.get_wallet(args.get("source", ""))
        dst = wallet_manager.get_wallet(args.get("destination", ""))
        payload = {"source": src.name if src else args.get("source"), "destination": dst.name if dst else args.get("destination"),
                   "payee_account": None, "amount": float(args.get("amount", 0))}
    else:
        payload = {"source": None, "destination": None, "payee_account": args.get("payee_account"), "amount": float(args.get("amount", 0))}
    return json.dumps(payload, sort_keys=True)


class Preflight:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def _needs_guardian(self, call: PlannedCall) -> bool:
        if call.tool == "transfer_external":
            return True
        if call.tool == "transfer_internal":
            src = wallet_manager.get_wallet(call.args.get("source", ""))
            if src and src.id == "emergency" and float(call.args.get("amount", 0)) > 0.5 * src.balance:
                return True
        return False

    def _is_duplicate(self, call: PlannedCall) -> bool:
        if call.tool not in MONEY_TOOLS:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        sig = SandboxAuditLogger.signature_digest(transfer_signature(call.tool, call.args))
        for e in SandboxAuditLogger.get_recent_logs(200):
            try:
                if datetime.fromisoformat(e.timestamp) < cutoff:
                    continue
            except Exception:
                continue
            if "EXECUTED" in e.status and e.details.get("signature") == sig:
                return True
        return False

    def _tier2_spent_today(self) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        total = 0.0
        for e in SandboxAuditLogger.get_recent_logs(500):
            if e.tier == "Tier 2" and "EXECUTED" in e.status and e.timestamp.startswith(today) and e.details.get("signature"):
                total += float(e.details.get("amount", 0.0))
        return total

    def check(self, calls: List[PlannedCall], ctx: AgentContext,
              guardian_results: Optional[Dict[int, dict]] = None) -> List[PreflightDecision]:
        decisions: List[PreflightDecision] = []
        guardian_results = guardian_results or {}
        for idx, call in enumerate(calls):
            errors = self.registry.validate(call)
            if errors:
                decisions.append(PreflightDecision(call, "Tier 3", "REJECT", errors))
                continue
            spec = self.registry.get(call.tool)
            tier = spec.tier(call.args, ctx)
            reasons: List[str] = [f"classified as {tier}"]

            # Evaluate Guardian first when required so scam messages without an account number are still LOCKED
            guardian = None
            if self._needs_guardian(call):
                guardian = guardian_results.get(idx)
                if guardian is not None:
                    same_amount = abs(float(guardian.get("amount", -1.0)) - float(call.args.get("amount", 0))) < 0.5
                    same_payee = (guardian.get("payee_account") or "") == (call.args.get("payee_account") or "")
                    if not (same_amount and same_payee):
                        guardian = None            # scan was for a different transfer; assess this one
                if guardian is None:
                    intent = TransferIntent(amount=float(call.args.get("amount", 0)), payee_name=call.args.get("payee_name", ""),
                                            payee_account=call.args.get("payee_account", ""), bank=call.args.get("bank", ""),
                                            note=call.args.get("note", ""))
                    guardian = Guardian.assess(intent, Evidence(text=call.args.get("evidence_text", "")), ctx).model_dump()

            if spec.dry_run:
                dr = spec.dry_run(call.args, ctx)
                if not dr.get("ok", True):
                    if guardian and guardian.get("locked"):
                        reasons.append(f"guardian risk {guardian['risk_score']}")
                        decisions.append(PreflightDecision(call, "Tier 3", "LOCKED", reasons + ["guardian lockdown"], guardian))
                        continue
                    decisions.append(PreflightDecision(call, tier, "REJECT", reasons + [f"dry-run failed: {dr.get('reason', dr)}"], guardian))
                    continue
                reasons.append("dry-run ok" + (f"; {dr['note']}" if dr.get("note") else ""))

            if guardian is not None:
                reasons.append(f"guardian risk {guardian['risk_score']}")
                if guardian["locked"]:
                    decisions.append(PreflightDecision(call, "Tier 3", "LOCKED", reasons + ["guardian lockdown"], guardian))
                    continue

            if self._is_duplicate(call):
                decisions.append(PreflightDecision(call, tier, "REJECT", reasons + ["duplicate of a transfer executed in the last 10 minutes"], guardian))
                continue
            if "INJECTION_SUSPECTED" in ctx.flags and tier != "Tier 1":
                decisions.append(PreflightDecision(call, tier, "AWAIT_HUMAN", reasons + ["injection suspected in this turn's inputs"], guardian))
                continue
            if tier == "Tier 2" and call.tool in MONEY_TOOLS and self._tier2_spent_today() + float(call.args.get("amount", 0)) > TIER2_DAILY_CAP_VND:
                decisions.append(PreflightDecision(call, tier, "AWAIT_HUMAN", reasons + ["Tier 2 daily cap exceeded"], guardian))
                continue
            if tier == "Tier 3":
                decisions.append(PreflightDecision(call, tier, "AWAIT_HUMAN", reasons + ["high-risk action requires human approval"], guardian))
                continue
            decisions.append(PreflightDecision(call, tier, "EXECUTE", reasons, guardian))
        return decisions

