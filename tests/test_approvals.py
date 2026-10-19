from datetime import datetime, timezone, timedelta
from app.agent.approvals import ApprovalQueue
from app.agent.executor import Executor
from app.agent.preflight import Preflight
from app.agent.tools import build_default_registry
from app.agent.types import AgentContext, PlannedCall, PreflightDecision
from app.agent.memory import ProfileStore
from app.core.sandbox_wallets import wallet_manager
import app.agent.approvals as approvals_mod


def ctx(tmp_path):
    store = ProfileStore(tmp_path / "p.json")
    approvals_mod.profile_store = store
    return AgentContext(session_id="s", transactions=[], profile=store.load(), flags=[])


def parts():
    reg = build_default_registry()
    return reg, Preflight(reg), Executor(reg)


def test_executor_runs_only_execute_and_captures_errors(tmp_path):
    reg, pf, ex = parts()
    good = PreflightDecision(PlannedCall("get_wallets", {}), "Tier 1", "EXECUTE")
    held = PreflightDecision(PlannedCall("cancel_subscription", {"merchant": "x"}), "Tier 2", "AWAIT_HUMAN")
    bad = PreflightDecision(PlannedCall("run_stress_test", {"months": "twelve"}), "Tier 1", "EXECUTE")
    results = ex.run([good, held, bad], ctx(tmp_path))
    assert [r.tool for r in results] == ["get_wallets", "run_stress_test"]
    assert results[0].error is None and results[1].error is not None


def test_approve_tier3_internal_transfer_executes(tmp_path):
    reg, pf, ex = parts()
    q = ApprovalQueue()
    c = ctx(tmp_path)
    before = wallet_manager.get_wallet("emergency").balance
    call = PlannedCall("transfer_internal", {"source": "Main Wallet", "destination": "Emergency Vault", "amount": 7_000_000})
    req = q.enqueue("s", pf.check([call], c)[0])
    assert req.status == "PENDING" and req.unlock["quiz_required"] is False
    out = q.decide(req.id, True, None, c, pf, ex, otp=q.issue_otp(req.id)["code"])
    assert out["status"] == "APPROVED"
    assert wallet_manager.get_wallet("emergency").balance == before + 7_000_000
    assert c.profile.approval_history[-1]["tool"] == "transfer_internal"


def test_locked_requires_cooling_off_and_quiz(tmp_path):
    reg, pf, ex = parts()
    q = ApprovalQueue()
    c = ctx(tmp_path)
    call = PlannedCall("transfer_external", {"payee_name": "Cong an", "payee_account": "0123456789", "amount": 50_000_000,
                                             "evidence_text": "cong an dieu tra, chuyen gap, tai khoan tam giu, giu bi mat"})
    d = pf.check([call], c)[0]
    assert d.verdict == "LOCKED"
    req = q.enqueue("s", d)
    assert req.unlock["quiz_required"] is True
    out = q.decide(req.id, True, [1, 2, 1], c, pf, ex, otp=q.issue_otp(req.id)["code"])
    assert out["status"] == "PENDING" and "cooling" in out["message"].lower()
    req.unlock["cooling_off_until"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    out = q.decide(req.id, True, [0, 0, 0], c, pf, ex, otp=q.issue_otp(req.id)["code"])
    assert out["status"] == "PENDING" and "quiz" in out["message"].lower()
    out = q.decide(req.id, True, [1, 2, 1], c, pf, ex, otp=q.issue_otp(req.id)["code"])
    assert out["status"] == "APPROVED" and out["result"].output["status"] == "EXECUTED"


def test_stale_approval_is_rejected_when_funds_gone(tmp_path):
    reg, pf, ex = parts()
    q = ApprovalQueue()
    c = ctx(tmp_path)
    fun = wallet_manager.get_wallet("fun")
    call = PlannedCall("transfer_internal", {"source": "Fun Wallet", "destination": "Main Wallet", "amount": 6_000_000})
    fun.balance = 10_000_000
    req = q.enqueue("s", pf.check([call], c)[0])
    fun.balance = 1_000
    out = q.decide(req.id, True, None, c, pf, ex, otp=q.issue_otp(req.id)["code"])
    assert out["status"] == "REJECTED" and any("dry-run" in r for r in out["reasons"])


def test_reject(tmp_path):
    reg, pf, ex = parts()
    q = ApprovalQueue()
    c = ctx(tmp_path)
    req = q.enqueue("s", PreflightDecision(PlannedCall("cancel_subscription", {"merchant": "x"}), "Tier 2", "AWAIT_HUMAN"))
    assert q.decide(req.id, False, None, c, pf, ex)["status"] == "REJECTED"
    assert q.list("PENDING") == []
