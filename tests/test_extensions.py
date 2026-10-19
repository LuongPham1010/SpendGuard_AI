"""Extensions after the review: payee reputation, replan, set_budget / explain_transaction."""
import json
from pathlib import Path

from app.agent.memory import UserProfile
from app.agent.orchestrator import build_agent
from app.agent.planner import RulePlanner
from app.agent.tools import build_default_registry
from app.agent.types import AgentContext
from app.modules.data_ingestion import DataIngestionEngine
from app.modules.guardian import Guardian, TransferIntent, Evidence
from app.modules.payee_reputation import PayeeReputation, LocalBlocklist


def txs():
    return DataIngestionEngine.load_default_transactions()


def ctx():
    return AgentContext("x", txs(), UserProfile(), [])


# ---------------- 1. payee reputation ----------------
def test_local_blocklist_lookup(tmp_path):
    bl = tmp_path / "bl.json"
    bl.write_text(json.dumps({"entries": [{"account": "0999888777", "bank": "vietcombank", "label": "impersonation",
                                            "source": "https://example.org/warning", "added": "2026-10-13"}]}), encoding="utf-8")
    rep = PayeeReputation(providers=[LocalBlocklist(bl)])
    hit = rep.lookup("0999888777", "vietcombank")
    assert hit["status"] == "blacklisted" and "example.org" in hit["source"]
    assert rep.lookup("0111111111", "acb")["status"] == "unknown"


def test_shipped_blocklist_is_valid_json_with_sources():
    data = json.loads(Path("data/guardian/payee_blocklist.json").read_text(encoding="utf-8"))
    assert data["entries"] and all({"account", "label", "source"} <= set(e) for e in data["entries"])


def test_blacklisted_payee_locks_even_with_innocent_text(monkeypatch):
    import app.modules.guardian as g
    monkeypatch.setattr(g, "payee_reputation", PayeeReputation(providers=[LocalBlocklist(Path("data/guardian/payee_blocklist.json"))]))
    account = json.loads(Path("data/guardian/payee_blocklist.json").read_text(encoding="utf-8"))["entries"][0]["account"]
    r = Guardian.assess(TransferIntent(amount=3_000_000, payee_account=account), Evidence(text="paying for the phone case"), ctx())
    assert r.features["payee_blacklisted"] == 1.0
    assert r.locked is True
    assert any("blocklist" in e.lower() or "reported" in e.lower() for e in r.evidence)


def test_check_payee_tool_registered():
    out = build_default_registry().get("check_payee").handler({"account": "0000000001", "bank": "acb"}, ctx())
    assert out["status"] in ("unknown", "clean", "blacklisted")


# ---------------- 2. replan ----------------
def test_rule_replan_adds_subscription_scan_when_wants_over_budget():
    turn = build_agent().run_turn("rp1", "how is my budget this month?", {}, txs())
    tools = [r["tool"] for r in turn.results]
    assert tools[0] == "get_budget_status" and "scan_subscriptions" in tools
    assert any(p["phase"] == "REPLAN" for p in turn.trace)
    assert turn.reflect["grounded"] is True


def test_replan_never_adds_money_tools():
    from app.agent.replan import rule_replan
    from app.agent.types import ToolResult
    budget = ToolResult("get_budget_status", {}, {"breakdown": {"Wants": {"status": "OVER_BUDGET"}}})
    extra = rule_replan("budget_status", [budget], ctx())
    assert extra and all(c.tool not in ("transfer_internal", "transfer_external", "cancel_subscription") for c in extra)


# ---------------- 3. set_budget / explain_transaction ----------------
def test_set_budget_intent_and_tool(tmp_path, monkeypatch):
    import app.agent.memory as memory_mod
    from app.agent.memory import ProfileStore
    store = ProfileStore(tmp_path / "p.json")
    monkeypatch.setattr(memory_mod, "profile_store", store)
    plan = RulePlanner(build_default_registry()).plan("set my dining budget to 4 million per month", AgentContext("t", [], None, []), {})
    assert plan.intent == "set_budget" and plan.calls[0].args == {"category": "Dining", "monthly_cap": 4_000_000}
    c = AgentContext("t", [], store.load(), [])
    out = build_default_registry().get("set_budget").handler({"category": "Dining", "monthly_cap": 4_000_000.0, "human_approved": False}, c)
    assert out["status"] == "SET" and store.load().budgets["Dining"] == 4_000_000


def test_set_budget_vietnamese_intent():
    plan = RulePlanner(build_default_registry()).plan("đặt ngân sách mua sắm 2 triệu mỗi tháng", AgentContext("t", [], None, []), {})
    assert plan.intent == "set_budget" and plan.calls[0].args["category"] == "Shopping" and plan.calls[0].args["monthly_cap"] == 2_000_000


def test_explain_transaction_intent_and_tool():
    plan = RulePlanner(build_default_registry()).plan("what is the spotify charge?", AgentContext("t", [], None, []), {})
    assert plan.intent == "explain_transaction" and "spotify" in plan.calls[0].args["query"].lower()
    out = build_default_registry().get("explain_transaction").handler({"query": "spotify"}, ctx())
    assert out["matches"] and out["matches"][0]["category"] == "Wants"
    assert out["recurring"] is True and out["occurrences"] >= 2


def test_explain_transaction_end_to_end_is_grounded():
    turn = build_agent().run_turn("ex1", "explain the spotify transaction", {}, txs())
    assert turn.intent == "explain_transaction" and turn.reflect["grounded"] is True and "Spotify" in turn.response
