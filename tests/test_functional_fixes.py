"""Regression tests for the functional review: install deps, subscription scope, reporting period, stress inputs,
planner coverage and honest cancellations."""
from pathlib import Path

from app.agent.memory import UserProfile
from app.agent.orchestrator import build_agent
from app.agent.playbooks import propose_month_actions
from app.agent.tools import build_default_registry, stress_inputs
from app.agent.types import AgentContext
from app.modules.data_ingestion import DataIngestionEngine
from app.modules.ghost_hunter import GhostSubscriptionHunter


def txs():
    return DataIngestionEngine.load_default_transactions()


def ctx():
    return AgentContext(session_id="t", transactions=txs(), profile=UserProfile(), flags=[])


def test_requirements_list_the_pdf_library_imported_at_startup():
    reqs = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text().lower()
    assert "pymupdf" in reqs


def test_rent_and_utilities_are_not_subscriptions():
    merchants = {s.merchant for s in GhostSubscriptionHunter.detect_subscriptions(txs())}
    assert "Vinhomes" not in merchants and "EVN" not in merchants
    assert {"Netflix", "Spotify", "California Fitness"} <= merchants


def test_budget_defaults_to_latest_month_with_income():
    out = build_default_registry().get("get_budget_status").handler({}, ctx())
    assert out["month"] == "2026-09"
    assert out["later_transactions"] == 1
    assert out["total_income"] == 41_200_000


def test_budget_whole_statement_on_request():
    out = build_default_registry().get("get_budget_status").handler({"month": "all"}, ctx())
    assert out["month"] == "all" and out["total_income"] == 111_200_000


def test_food_question_reports_dining_and_groceries():
    turn = build_agent().run_turn("f1", "tháng này tôi tiêu bao nhiêu tiền ăn uống?", {}, txs())
    cs = turn.results[0]["output"]["category_spend"]
    assert cs["category"] == "Food" and cs["amount"] > 0
    assert turn.response.startswith("Food spending")


def test_stress_test_and_month_review_share_inputs():
    c = ctx()
    tool = build_default_registry().get("run_stress_test").handler({}, c)
    review = propose_month_actions(c)
    assert tool["resilience_score"] == review.stress["resilience_score"]
    assert tool["inputs"]["monthly_income"] == stress_inputs(c)["monthly_income"]


def test_job_loss_scenario_is_simulated():
    agent = build_agent()
    base = agent.run_turn("j0", "run a stress test", {}, txs()).results[0]["output"]
    turn = agent.run_turn("j1", "what if I lose my job for 3 months?", {}, txs())
    assert turn.plan[0]["args"] == {"income_loss_months": 3}
    assert turn.results[0]["output"]["resilience_score"] < base["resilience_score"]
    assert "no income for the first 3" in turn.response


def test_money_question_shows_wallets():
    turn = build_agent().run_turn("w1", "how much money do I have?", {}, txs())
    assert turn.intent == "wallets" and "Main Wallet" in turn.response


def test_task_scam_without_transfer_verb_reaches_guardian():
    turn = build_agent().run_turn("t1", "Em được nhận việc làm online, cần nạp 5 triệu để nhận nhiệm vụ, "
                                        "hoa hồng 30%/ngày, stk 1112223334 ACB", {}, txs())
    verdicts = {d["call"]["tool"]: d["verdict"] for d in turn.decisions}
    assert turn.intent == "transfer_external"
    assert verdicts["transfer_external"] == "LOCKED"


def test_vietnamese_cancel_resolves_the_merchant_and_drafts_notice():
    turn = build_agent().run_turn("c1", "Hủy netflix giúp tôi", {}, txs())
    assert turn.plan[0]["args"]["merchant"] == "Netflix"
    assert "FLAGGED_FOR_CANCELLATION" in turn.response and "Subject:" in turn.response


def test_cancelling_an_unknown_merchant_is_rejected():
    turn = build_agent().run_turn("c2", "cancel my gym abc subscription", {}, txs())
    assert turn.decisions[0]["verdict"] == "REJECT"
    assert "FLAGGED_FOR_CANCELLATION" not in turn.response
