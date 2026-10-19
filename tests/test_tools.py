from app.agent.types import PlannedCall, AgentContext
from app.agent.tools import build_default_registry
from app.modules.data_ingestion import DataIngestionEngine


def ctx():
    return AgentContext(session_id="t", transactions=DataIngestionEngine.load_default_transactions(), profile=None, flags=[])


def test_registry_has_all_tools():
    reg = build_default_registry()
    expected = {"get_transactions", "get_budget_status", "scan_subscriptions", "cancel_subscription",
                "run_stress_test", "get_wallets", "transfer_internal", "transfer_external",
                "guardian_scan", "second_opinion", "read_receipt", "read_chat_screenshot", "remember", "recall"}
    assert expected.issubset(set(reg.names()))


def test_validate_rejects_unknown_tool_and_bad_args():
    reg = build_default_registry()
    assert reg.validate(PlannedCall(tool="nope", args={})) == ["unknown tool: nope"]
    errs = reg.validate(PlannedCall(tool="transfer_internal", args={"amount": "lots"}))
    assert any("amount" in e for e in errs)


def test_transfer_internal_tier_depends_on_amount():
    reg = build_default_registry()
    spec = reg.get("transfer_internal")
    assert spec.tier({"amount": 1_000_000}, ctx()) == "Tier 2"
    assert spec.tier({"amount": 6_000_000}, ctx()) == "Tier 3"


def test_get_budget_status_returns_numbers_from_categorizer():
    reg = build_default_registry()
    out = reg.get("get_budget_status").handler({}, ctx())
    assert out["total_income"] > 0 and "breakdown" in out


def test_function_declarations_are_json_schema():
    reg = build_default_registry()
    decls = reg.function_declarations()
    t = next(d for d in decls if d["name"] == "transfer_internal")
    assert t["parameters"]["properties"]["amount"]["type"] == "number"


def test_array_params_declare_items_for_function_calling():
    reg = build_default_registry()
    for d in reg.function_declarations():
        for name, prop in d["parameters"]["properties"].items():
            if prop.get("type") == "array":
                assert "items" in prop, f"{d['name']}.{name} array without items"
