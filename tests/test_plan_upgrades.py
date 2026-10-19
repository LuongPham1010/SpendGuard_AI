"""Submission-readiness upgrades: proactive scan of past payments, masked audit log, simulated OTP for approvals,
Tier 2 notifications, circuit breaker and English-only replies."""
import json

from fastapi.testclient import TestClient

from app.agent.approvals import ApprovalQueue
from app.agent.executor import Executor
from app.agent.memory import UserProfile
from app.agent.orchestrator import Orchestrator, build_agent
from app.agent.preflight import Preflight, transfer_signature
from app.agent.reflect import render_template
from app.agent.tools import ToolSpec, build_default_registry, scan_past_payments
from app.agent.types import AgentContext, Plan, PlannedCall, PreflightDecision
from app.core.audit_logger import SandboxAuditLogger
from app.core.notifications import notifications
from app.main import app
from app.modules.data_ingestion import DataIngestionEngine


def txs():
    return DataIngestionEngine.load_default_transactions()


def ctx():
    return AgentContext(session_id="t", transactions=txs(), profile=UserProfile(), flags=[])


# ---- A1: proactive scan of payments already made ----
def test_past_scan_flags_only_the_telegram_investment_payment():
    out = scan_past_payments(ctx())
    assert [x["id"] for x in out["flagged"]] == ["TX1050"]
    assert out["flagged_total"] == 25_000_000 and out["advice"]


def test_month_review_opens_with_the_scam_warning():
    turn = build_agent().run_turn("m1", "run my month", {}, txs())
    assert turn.plan[0]["tool"] == "scan_past_transactions" and turn.plan[-1]["tool"] == "run_my_month_report"
    assert turn.response.startswith("Warning: 1 payment(s)")
    assert "25,000,000 VND to Unknown Telegram Entity" in turn.response
    assert turn.reflect["grounded"] is True


def test_vietnamese_scam_question_routes_to_the_past_scan():
    turn = build_agent().run_turn("m2", "kiểm tra giúp tôi có khoản lừa đảo nào không", {}, txs())
    assert turn.intent == "scan_past_transactions" and "Unknown Telegram Entity" in turn.response


def test_past_scan_does_not_feed_guardian_velocity():
    scan_past_payments(ctx())
    assert not [e for e in SandboxAuditLogger.get_recent_logs(50) if e.module == "Guardian"]


# ---- A5: masked audit log ----
def test_audit_log_masks_account_numbers_everywhere():
    e = SandboxAuditLogger.log_event(tier="Tier 3", module="T", action="A", status="S",
                                     details={"recipient": "0123456789", "note": "stk 1112223334 ACB", "nested": ["99887766554"]})
    dumped = json.dumps(e.details)
    for raw in ("0123456789", "1112223334", "99887766554"):
        assert raw not in dumped
    assert e.details["recipient"] == "012****789"


def test_duplicate_detection_still_works_with_signature_digest():
    args = {"payee_name": "Shop", "payee_account": "4455667788", "amount": 1_000_000}
    SandboxAuditLogger.log_event(tier="Tier 3", module="SandboxWallets", action="EXTERNAL_TRANSFER", status="HUMAN_APPROVED_EXECUTED",
                                 details={"amount": 1_000_000, "signature": transfer_signature("transfer_external", args)})
    stored = SandboxAuditLogger.get_recent_logs(1)[0].details["signature"]
    assert stored.startswith("sig:") and "4455667788" not in stored
    assert Preflight(build_default_registry())._is_duplicate(PlannedCall("transfer_external", args))


def test_chain_verifier_accepts_a_clean_log_and_spots_tampering(tmp_path, monkeypatch):
    import app.core.audit_logger as audit_mod
    from scripts.verify_audit_chain import GENESIS, verify
    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_mod, "EXECUTION_LOG_FILE", log)
    monkeypatch.setattr(SandboxAuditLogger, "_last_hash", GENESIS)
    for i in range(3):
        SandboxAuditLogger.log_event(tier="Tier 2", module="T", action="A", status="EXECUTED", details={"amount": 1000 * i})
    assert verify(log)[0] is True
    log.write_text(log.read_text(encoding="utf-8").replace('"amount": 1000', '"amount": 9000'), encoding="utf-8")
    ok, _, msg = verify(log)
    assert ok is False and "line 2" in msg


# ---- A2: simulated OTP for every approval ----
def _queued(q, c, amount=7_000_000):
    reg = build_default_registry()
    pf, ex = Preflight(reg), Executor(reg)
    call = PlannedCall("transfer_internal", {"source": "Main Wallet", "destination": "Emergency Vault", "amount": amount})
    return q.enqueue("s", pf.check([call], c)[0]), pf, ex


def test_approval_needs_a_valid_one_time_code():
    q, c = ApprovalQueue(), ctx()
    req, pf, ex = _queued(q, c)
    assert req.unlock["otp_required"] is True
    out = q.decide(req.id, True, None, c, pf, ex)
    assert out["status"] == "PENDING" and out.get("otp_required")
    code = q.issue_otp(req.id)["code"]
    wrong = "000000" if code != "000000" else "111111"
    assert q.decide(req.id, True, None, c, pf, ex, otp=wrong)["status"] == "PENDING"
    assert q.decide(req.id, True, None, c, pf, ex, otp=code)["status"] == "APPROVED"


def test_three_wrong_codes_invalidate_the_otp():
    q, c = ApprovalQueue(), ctx()
    req, pf, ex = _queued(q, c)
    code = q.issue_otp(req.id)["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(3):
        out = q.decide(req.id, True, None, c, pf, ex, otp=wrong)
    assert "three times" in out["message"]
    assert q.decide(req.id, True, None, c, pf, ex, otp=code)["status"] == "PENDING"   # the old code is gone


def test_approval_listing_never_exposes_otp_state():
    with TestClient(app) as client:
        body = client.post("/api/agent/chat", data={"text": "move 7 million from main wallet to emergency vault", "session_id": "otp1"}).json()
        rid = body["queued"][0]["id"]
        client.post(f"/api/agent/approvals/{rid}/otp")
        listing = json.dumps(client.get("/api/agent/approvals").json())
        assert "hash" not in listing and "attempts" not in listing


# ---- A3: Tier 2 notifications ----
def test_tier2_action_sends_a_notification():
    notifications.clear()
    build_agent().run_turn("n1", "move 2 million from main wallet to emergency vault", {}, txs())
    items = notifications.list()
    assert items and items[0]["kind"] == "auto" and items[0]["tier"] == "Tier 2"
    with TestClient(app) as client:
        assert client.get("/api/notifications").json()["unread"] >= 1
        assert client.post("/api/notifications/read").json()["unread"] == 0


# ---- A4: circuit breaker ----
def test_circuit_breaker_stops_the_turn_after_two_errors():
    reg = build_default_registry()

    def boom(a, c):
        raise RuntimeError("upstream down")

    reg.register(ToolSpec("boom", "always fails", {"type": "object", "properties": {}, "required": []}, lambda a, c: "Tier 1", boom))

    class FixedPlanner:
        def plan(self, text, ctx, attachments, history=None):
            return Plan("budget_status", [PlannedCall("boom"), PlannedCall("boom"), PlannedCall("get_wallets")])

    orch = Orchestrator(reg, FixedPlanner(), Preflight(reg), Executor(reg), ApprovalQueue())
    turn = orch.run_turn("cb", "anything", {}, txs())
    assert "CIRCUIT_OPEN" in turn.flags
    assert turn.decisions[2]["verdict"] == "REJECT" and "circuit breaker" in turn.decisions[2]["reasons"][0]
    assert not any(t["phase"] == "REPLAN" for t in turn.trace)
    assert len(turn.results) == 2


# ---- A6: English-only replies ----
def test_missing_account_reply_is_english():
    call = PlannedCall("transfer_external", {"payee_name": "Lan", "amount": 2_000_000})
    dec = PreflightDecision(call, "Tier 3", "REJECT", ["dry-run failed: missing beneficiary account number (STK) for 'Lan'"])
    text = render_template("transfer_external", Plan("transfer_external", [call]), [], [dec], [])
    assert "without their account number" in text and "Vui lòng" not in text
