from app.agent.planner import RulePlanner, extract_amount, extract_payee
from app.agent.tools import build_default_registry
from app.agent.types import AgentContext


def ctx():
    return AgentContext(session_id="t", transactions=[], profile=None, flags=[])


def test_extract_amount_vietnamese_units():
    assert extract_amount("chuyển 50 triệu") == 50_000_000
    assert extract_amount("gui 2tr5") == 2_500_000
    assert extract_amount("pay 1,200,000 VND") == 1_200_000
    assert extract_amount("1.5 tỷ") == 1_500_000_000
    assert extract_amount("no money here") is None


def test_extract_payee_account_and_bank():
    p = extract_payee("transfer to Nguyen Van A account 0123456789 at Vietcombank")
    assert p["payee_account"] == "0123456789" and p["bank"] == "vietcombank"
    assert "nguyen van a" in p["payee_name"]


def test_budget_intent():
    plan = RulePlanner(build_default_registry()).plan("How is my budget this month?", ctx(), {})
    assert plan.intent == "budget_status"
    assert [c.tool for c in plan.calls] == ["get_budget_status"]


def test_external_transfer_intent_includes_guardian_then_transfer():
    plan = RulePlanner(build_default_registry()).plan(
        "Chuyển 50 triệu cho công an, stk 0123456789 Vietcombank, họ nói tài khoản tạm giữ", ctx(), {})
    assert plan.intent == "transfer_external"
    assert [c.tool for c in plan.calls] == ["guardian_scan", "transfer_external"]
    assert plan.calls[1].args["amount"] == 50_000_000


def test_screenshot_attachment_adds_read_chat_screenshot_first():
    plan = RulePlanner(build_default_registry()).plan(
        "send 20 million to account 999888777 Techcombank", ctx(), {"shot1": b"img"})
    assert [c.tool for c in plan.calls] == ["read_chat_screenshot", "guardian_scan", "transfer_external"]


def test_internal_transfer_intent():
    plan = RulePlanner(build_default_registry()).plan("move 3 million from main wallet to emergency vault", ctx(), {})
    assert plan.calls[0].tool == "transfer_internal"
    assert plan.calls[0].args["source"] == "Main Wallet"
    assert plan.calls[0].args["destination"] == "Emergency Vault"
    assert plan.calls[0].args["amount"] == 3_000_000


def test_run_my_month_intent():
    plan = RulePlanner(build_default_registry()).plan("run my month", ctx(), {})
    assert plan.intent == "run_my_month"


def test_unknown_intent_has_no_calls():
    plan = RulePlanner(build_default_registry()).plan("tell me a joke", ctx(), {})
    assert plan.intent == "unknown" and plan.calls == []
