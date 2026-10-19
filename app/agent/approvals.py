"""Human-in-the-loop queue for Tier 3 and Guardian-locked actions."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

import app.agent.memory as memory_mod
from app.agent.executor import Executor
from app.agent.preflight import Preflight
from app.agent.types import AgentContext, PlannedCall, PreflightDecision
from app.core.audit_logger import SandboxAuditLogger
from app.modules.anti_scam_shield import AntiScamShield

# Resolved at call time through this module's attribute so tests can swap the store.
profile_store = memory_mod.profile_store

OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 3


def _otp_hash(request_id: str, code: str) -> str:
    return hashlib.sha256(f"{request_id}:{code}".encode("utf-8")).hexdigest()


class ApprovalRequest(BaseModel):
    id: str
    created_at: str
    session_id: str
    tool: str
    args: Dict[str, Any]
    tier: str
    verdict: str
    reasons: List[str] = Field(default_factory=list)
    guardian: Optional[Dict[str, Any]] = None
    status: str = "PENDING"
    unlock: Dict[str, Any] = Field(default_factory=dict)


class ApprovalQueue:
    def __init__(self):
        self._items: Dict[str, ApprovalRequest] = {}
        self._otp: Dict[str, Dict[str, Any]] = {}      # request id -> {hash, expires, attempts}; never serialised

    def enqueue(self, session_id: str, d: PreflightDecision) -> ApprovalRequest:
        locked = d.verdict == "LOCKED"
        cooling = None
        if locked and d.guardian:
            cooling = (datetime.now(timezone.utc) + timedelta(seconds=int(d.guardian.get("cooling_off_seconds", 60)))).isoformat()
        req = ApprovalRequest(id=uuid.uuid4().hex[:10], created_at=datetime.now(timezone.utc).isoformat(),
                              session_id=session_id, tool=d.call.tool, args=dict(d.call.args), tier=d.tier,
                              verdict=d.verdict, reasons=list(d.reasons), guardian=d.guardian,
                              unlock={"quiz_required": locked, "cooling_off_until": cooling, "otp_required": True})
        self._items[req.id] = req
        SandboxAuditLogger.log_event(tier=d.tier, module="ApprovalQueue", action="REQUEST_QUEUED", status=d.verdict,
                                     details={"request_id": req.id, "tool": req.tool, "amount": req.args.get("amount")})
        return req

    def list(self, status: str = "PENDING") -> List[ApprovalRequest]:
        return [r for r in self._items.values() if r.status == status]

    def get(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._items.get(request_id)

    def issue_otp(self, request_id: str) -> Dict[str, Any]:
        """Create a one-time code for a pending request. The sandbox has no SMS gateway, so the code is returned
        to the caller labelled as a simulated SMS; only its hash is kept."""
        req = self._items.get(request_id)
        if not req or req.status != "PENDING":
            return {"status": "NOT_FOUND", "message": "No pending request with that id."}
        code = f"{secrets.randbelow(10 ** 6):06d}"
        expires = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)
        self._otp[request_id] = {"hash": _otp_hash(request_id, code), "expires": expires, "attempts": 0}
        SandboxAuditLogger.log_event(tier=req.tier, module="ApprovalQueue", action="OTP_ISSUED", status="SIMULATED_SMS",
                                     details={"request_id": req.id, "ttl_seconds": OTP_TTL_SECONDS})
        return {"status": "SENT", "channel": "simulated SMS", "code": code, "expires_at": expires.isoformat(),
                "message": f"[simulated SMS] Your SpendGuard approval code is {code}. It expires in {OTP_TTL_SECONDS // 60} minutes."}

    def _otp_ok(self, request_id: str, otp: Optional[str]) -> Optional[str]:
        """None when the code is valid (and consumed); otherwise the reason it was refused."""
        state = self._otp.get(request_id)
        if not state or state["expires"] < datetime.now(timezone.utc):
            self._otp.pop(request_id, None)
            return "One-time code missing or expired. Request a new code."
        if not otp or _otp_hash(request_id, str(otp).strip()) != state["hash"]:
            state["attempts"] += 1
            if state["attempts"] >= OTP_MAX_ATTEMPTS:
                self._otp.pop(request_id, None)
                return "Wrong one-time code three times. Request a new code."
            return "Wrong one-time code."
        self._otp.pop(request_id, None)
        return None

    @staticmethod
    def _quiz_ok(answers: Optional[List[int]]) -> bool:
        if not answers or len(answers) != len(AntiScamShield.COGNITIVE_QUIZ):
            return False
        return all(a == q.correct_option_index for a, q in zip(answers, AntiScamShield.COGNITIVE_QUIZ))

    def decide(self, request_id: str, approve: bool, quiz_answers: Optional[List[int]], ctx: AgentContext,
               preflight: Preflight, executor: Executor, otp: Optional[str] = None) -> Dict[str, Any]:
        import app.agent.approvals as this_mod
        store = this_mod.profile_store
        req = self._items.get(request_id)
        if not req or req.status != "PENDING":
            return {"status": "NOT_FOUND", "result": None, "message": "No pending request with that id.", "reasons": []}
        if not approve:
            req.status = "REJECTED"
            SandboxAuditLogger.log_event(tier=req.tier, module="ApprovalQueue", action="REQUEST_DECIDED", status="REJECTED_BY_USER",
                                         details={"request_id": req.id, "tool": req.tool})
            return {"status": "REJECTED", "result": None, "message": "Action rejected by the user.", "reasons": []}
        if req.unlock.get("quiz_required"):
            until = req.unlock.get("cooling_off_until")
            if until and datetime.fromisoformat(until) > datetime.now(timezone.utc):
                return {"status": "PENDING", "result": None, "message": f"Cooling-off period active until {until}.", "reasons": []}
            if not self._quiz_ok(quiz_answers):
                return {"status": "PENDING", "result": None, "message": "Safety quiz not passed. Review the explanations and try again.", "reasons": []}
        if req.unlock.get("otp_required"):
            refused = self._otp_ok(request_id, otp)
            if refused:
                SandboxAuditLogger.log_event(tier=req.tier, module="ApprovalQueue", action="OTP_CHECK", status="REFUSED",
                                             details={"request_id": req.id, "reason": refused})
                return {"status": "PENDING", "result": None, "message": refused, "reasons": [], "otp_required": True}
        call = PlannedCall(req.tool, dict(req.args))
        recheck = preflight.check([call], ctx)[0]
        if recheck.verdict == "REJECT":
            req.status = "REJECTED"
            SandboxAuditLogger.log_event(tier=req.tier, module="ApprovalQueue", action="REQUEST_DECIDED", status="REJECTED_STALE",
                                         details={"request_id": req.id, "reasons": recheck.reasons})
            return {"status": "REJECTED", "result": None, "message": "State changed since the request was queued.", "reasons": recheck.reasons}
        result = executor.run_one(call, ctx, human_approved=True)
        status = str(result.output.get("status", "")).upper()
        handler_refused = result.output.get("success") is False or status.startswith(("REJECTED", "REFUSED", "FAILED"))
        executed = result.error is None and not handler_refused
        req.status = "APPROVED" if executed else "REJECTED"
        ctx.profile.approval_history.append({"request_id": req.id, "tool": req.tool, "amount": req.args.get("amount"),
                                             "decided_at": datetime.now(timezone.utc).isoformat(), "status": req.status})
        store.save(ctx.profile)
        SandboxAuditLogger.log_event(tier=req.tier, module="ApprovalQueue", action="REQUEST_DECIDED", status=req.status,
                                     details={"request_id": req.id, "tool": req.tool, "error": result.error})
        message = "Executed with human approval." if executed else (result.error or result.output.get("message") or "Execution refused.")
        return {"status": req.status, "result": result, "message": message, "reasons": [] if executed else [message]}


approval_queue = ApprovalQueue()
