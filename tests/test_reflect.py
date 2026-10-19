from app.agent.reflect import Reflector, extract_numbers, collect_numbers, render_template
from app.agent.types import ToolResult, Plan, PlannedCall, PreflightDecision


def test_extract_numbers_formats():
    nums = extract_numbers("You spent 3,200,000 VND (12.5%) and saved 2.5 million; 50 triệu pending")
    assert 3_200_000 in nums and 12.5 in nums and 2_500_000 in nums and 50_000_000 in nums


def test_collect_numbers_nested():
    assert {1.0, 2.5, 7.0}.issubset(collect_numbers({"a": {"b": [1, 2.5, {"c": 7}]}, "d": "x"}))


def test_grounded_narrative_passes():
    r = ToolResult("get_budget_status", {}, {"total_income": 35_000_000, "savings_rate_pct": 12.5})
    rep = Reflector.check("Income was 35,000,000 VND and the savings rate is 12.5%.", [r])
    assert rep.grounded and rep.unmatched == []


def test_hallucinated_number_fails_and_is_regenerated():
    r = ToolResult("get_budget_status", {}, {"total_income": 35_000_000, "total_expense": 22_000_000,
                                             "savings_rate_pct": 12.5, "breakdown": {}, "suggested_savings_sweep_vnd": 0})
    text, rep = Reflector.finalize("Income was 35,000,000 VND and you overspent by 9,999,999 VND.",
                                   "budget_status", Plan("budget_status", [PlannedCall("get_budget_status")]), [r], [], [])
    assert rep.grounded is False and 9_999_999 in rep.unmatched and rep.regenerated is True
    assert "35,000,000" in text and "9,999,999" not in text


def test_template_for_locked_transfer_mentions_freeze():
    r = ToolResult("guardian_scan", {}, {"risk_score": 91.0, "locked": True, "scam_type": "authority_impersonation",
                                         "counter_facts": ["Police never ask for transfers."], "evidence": ["Matched pattern 'authority_impersonation'"]})
    text = render_template("transfer_external", Plan("transfer_external", []), [r], [], [])
    assert "frozen" in text.lower() and "91" in text and "Police never ask" in text


def test_absolute_value_of_negative_output_is_grounded():
    r = ToolResult("get_budget_status", {}, {"net_surplus": -17_649_000})
    rep = Reflector.check("You are 17,649,000 VND short this month.", [r])
    assert rep.grounded


def test_template_for_ambiguous_transfer_shows_candidates():
    call = PlannedCall("transfer_external", {"payee_name": "Tuấn", "amount": 500000})
    reason = "dry-run failed: ambiguous beneficiary 'Tuấn': found 2 matching accounts [1. Nguyễn Văn Tuấn (Vietcombank - STK 012****789); 2. Lê Minh Tuấn (Vietcombank - STK 077****999)]"
    dec = PreflightDecision(call, "Tier 3", "REJECT", [reason])
    text = render_template("transfer_external", Plan("transfer_external", [call]), [], [dec], [])
    assert "Found 2 saved contacts named 'Tuấn'" in text
    assert "1. Nguyễn Văn Tuấn" in text and "2. Lê Minh Tuấn" in text


def test_orchestrator_preserves_clarification_bubble_when_rejected(monkeypatch):
    import app.agent.orchestrator as orch_mod
    import app.agent.memory as mem_mod
    from app.agent.memory import UserProfile, PayeeRecord
    from app.core.llm_gateway import LLMGateway, LLMResult

    class DummyNarratorBackend:
        name = "dummy"

        def complete(self, prompt, images, schema, tools):
            # Simulate Gemini trying to overwrite the response with generic wallet summary
            return LLMResult(available=True, text="The transaction of 500,000 VND has a LOW risk evaluation.", model="dummy")

    fake_profile = UserProfile(
        known_payees={
            "0123456789": PayeeRecord(name="Nguyễn Văn Tuấn", account_masked="012****789", first_seen="2026-08-01T00:00:00Z", bank="Vietcombank"),
            "0777888999": PayeeRecord(name="Lê Minh Tuấn", account_masked="077****999", first_seen="2026-08-02T00:00:00Z", bank="Vietcombank"),
        }
    )
    monkeypatch.setattr(mem_mod.profile_store, "load", lambda: fake_profile)
    monkeypatch.setattr(orch_mod, "gateway", LLMGateway(DummyNarratorBackend()))

    ag = orch_mod.build_agent()
    turn = ag.run_turn("test-session-ambig", "Chuyển cho Tuấn Vietcombank 500k", {}, [])
    assert any(d["verdict"] == "REJECT" for d in turn.decisions)
    assert "Nguyễn Văn Tuấn" in turn.response
    assert "Lê Minh Tuấn" in turn.response
    assert "Who should receive it?" in turn.response
