from app.agent.playbooks import propose_month_actions, expand_run_my_month
from app.agent.orchestrator import build_agent
from app.agent.types import AgentContext
from app.agent.memory import UserProfile
from app.modules.data_ingestion import DataIngestionEngine


def ctx():
    p = UserProfile()
    p.facts["unused_subscriptions"] = "California Fitness"
    return AgentContext("m", DataIngestionEngine.load_default_transactions(), p, [])


def test_proposal_contains_sweep_and_cancellation():
    prop = propose_month_actions(ctx())
    tools = [c.tool for c in prop.actions]
    assert "transfer_internal" in tools and "cancel_subscription" in tools
    sweep = next(c for c in prop.actions if c.tool == "transfer_internal")
    assert 0 < sweep.args["amount"] <= 5_000_000


def test_expand_ends_with_report_call():
    plan = expand_run_my_month(ctx())
    assert plan.intent == "run_my_month" and plan.calls[-1].tool == "run_my_month_report"


def test_run_my_month_turn_executes_tier2_and_reports():
    turn = build_agent().run_turn("m1", "run my month", {}, DataIngestionEngine.load_default_transactions())
    executed = [r["tool"] for r in turn.results]
    assert "transfer_internal" in executed and "run_my_month_report" in executed
    assert turn.reflect["grounded"] is True
    assert "Emergency Vault" in turn.response
