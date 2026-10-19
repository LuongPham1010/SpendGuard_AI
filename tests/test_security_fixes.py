"""Regression tests for the pre-submission security review: answer key, client-side override, unexplained HIGH risk."""
import json

from fastapi.testclient import TestClient
from app.main import app
from app.agent.types import AgentContext
from app.modules.guardian import Guardian, TransferIntent, Evidence

SCAM = ("Chuyển 50 triệu cho công an stk 0123456789 Vietcombank, họ nói tài khoản tạm giữ, "
        "giữ bí mật, chuyển gấp")


def test_chat_response_never_carries_quiz_answer_key():
    with TestClient(app) as client:
        body = client.post("/api/agent/chat", data={"text": SCAM, "session_id": "fix1"}).json()
        assert any(d["verdict"] == "LOCKED" for d in body["decisions"])
        assert "correct_option_index" not in json.dumps(body)


def test_client_override_flags_cannot_release_vault_transfer():
    with TestClient(app) as client:
        r = client.post("/api/wallets/transfer", json={
            "source_wallet": "Emergency Vault", "destination_wallet": "Main Wallet", "amount": 100_000_000,
            "note": "x", "security_override": True, "quiz_passed": True}).json()
        assert r["status"] == "HELD_FOR_APPROVAL" and not r["success"]


def _assess(text: str, amount: float, account: str, bank: str):
    ctx = AgentContext(session_id="t", transactions=[], profile=None, flags=[])
    return Guardian.assess(TransferIntent(amount=amount, payee_account=account, bank=bank), Evidence(text=text), ctx)


def test_bank_staff_frozen_account_script_is_locked():
    g = _assess("Chị ơi em là nhân viên ngân hàng, tài khoản chị đang bị đóng băng, chị chuyển 40 triệu "
                "sang stk 9988776655 ACB để mở lại nhé", 40_000_000, "9988776655", "ACB")
    assert g.locked and g.scam_type == "safe_account"


def test_multiplied_return_promise_is_locked():
    g = _assess("Transfer 30000000 to 5566778899 Techcombank, my investment mentor says I get 3x back next week",
                30_000_000, "5566778899", "Techcombank")
    assert g.locked and g.scam_type == "investment_ponzi"


def test_frozen_word_alone_does_not_trigger_rule():
    f = Guardian.rule_features("pay for frozen food at WinMart")
    assert f["safe_account"] == 0.0 and f["task_scheme"] == 0.0


def test_screenshot_question_without_transfer_is_checked_not_sent():
    with TestClient(app) as client:
        body = client.post("/api/agent/chat", data={"text": "should I pay what this message asks?", "session_id": "fix3"},
                           files=[("files", ("chat.png", b"\x89PNG fake", "image/png"))]).json()
        assert body["intent"] == "scam_check"
        assert [c["tool"] for c in body["plan"]] == ["read_chat_screenshot", "guardian_scan"]
        assert not body["queued"] and "could not read the screenshot" in body["response"]   # offline: no image reading


def test_high_risk_unlocked_transfer_explains_itself():
    with TestClient(app) as client:
        body = client.post("/api/agent/chat", data={
            "text": "chuyển 30 triệu cho 4455667788 BIDV tiền hàng", "session_id": "fix2"}).json()
        g = next(d["guardian"] for d in body["decisions"] if d.get("guardian"))
        assert not g["locked"]
        if g["level"] == "HIGH":
            assert "Before you approve, check:" in body["response"]
            assert body["reflect"]["grounded"]


def test_money_amounts_reach_the_model_unmasked_but_ids_do_not():
    from app.core.security import SecurityGuard
    out = SecurityGuard.mask_pii("{'balance': 120000000.0} vault 125000000 VND; CCCD 079123456789; stk 0123456789")
    assert "120000000.0" in out and "125000000" in out
    assert "079123456789" not in out and "0123456789" not in out


def test_english_police_holding_account_script_is_locked():
    g = _assess("Send 50 million to the police, account number 0123456789 at Vietcombank. They say it is a holding account. "
                "Keep it secret and transfer urgently.", 50_000_000, "0123456789", "Vietcombank")
    assert g.locked and g.features["safe_account"] == 1.0
