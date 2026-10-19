from app.agent.planner import LLMPlanner, RulePlanner
from app.agent.tools import build_default_registry
from app.agent.types import AgentContext
from app.core.llm_gateway import LLMGateway, LLMResult
import app.agent.planner as planner_mod


class FakeBackend:
    name = "fake"

    def __init__(self, calls):
        self.calls = calls

    def complete(self, prompt, images, schema, tools):
        return LLMResult(available=True, function_calls=self.calls, model="fake")


def ctx():
    return AgentContext("t", [], None, [])


def test_llm_plan_is_validated_and_used(monkeypatch):
    reg = build_default_registry()
    monkeypatch.setattr(planner_mod, "gateway", LLMGateway(FakeBackend([{"name": "get_budget_status", "args": {}}])))
    plan = LLMPlanner(reg, RulePlanner(reg)).plan("budget?", ctx(), {})
    assert plan.source == "llm" and plan.calls[0].tool == "get_budget_status"


def test_invalid_llm_plan_falls_back_to_rules(monkeypatch):
    reg = build_default_registry()
    monkeypatch.setattr(planner_mod, "gateway", LLMGateway(FakeBackend([{"name": "nuke", "args": {}}])))
    plan = LLMPlanner(reg, RulePlanner(reg)).plan("how is my budget", ctx(), {})
    assert plan.source == "rule" and plan.intent == "budget_status"


def test_gemini_backend_module_imports_without_network():
    from app.core.gemini_backend import GeminiBackend
    assert GeminiBackend.name == "gemini"


def test_llm_plan_missing_money_tool_for_transfer_falls_back_to_rules(monkeypatch):
    reg = build_default_registry()
    monkeypatch.setattr(planner_mod, "gateway", LLMGateway(FakeBackend([{"name": "guardian_scan", "args": {"amount": 50000000.0}}])))
    plan = LLMPlanner(reg, RulePlanner(reg)).plan("send 50 million to account 0123456789 Vietcombank", ctx(), {})
    assert plan.source == "rule"
    assert [c.tool for c in plan.calls] == ["guardian_scan", "transfer_external"]


def test_gemini_backend_rotates_keys_on_quota_errors():
    from app.core.gemini_backend import GeminiBackend

    class Boom(Exception):
        pass

    class FakeModels:
        def __init__(self, fail):
            self.fail = fail
            self.calls = 0

        def generate_content(self, model, contents, config):
            self.calls += 1
            if self.fail:
                raise Boom("429 RESOURCE_EXHAUSTED")
            class R:
                candidates = []
                text = "ok"
            return R()

    class FakeClient:
        def __init__(self, fail):
            self.models = FakeModels(fail)

    b = GeminiBackend(api_key="k1", models=["m1"], extra_keys=["k2"])
    b.clients = [FakeClient(fail=True), FakeClient(fail=False)]
    res = b.complete("prompt", [], None, None)
    assert res.available is True and res.text == "ok"
    assert b.clients[0].models.calls == 1 and b.clients[1].models.calls == 1


def test_remember_command_is_stored_as_typed_even_if_the_model_renames_it(monkeypatch):
    reg = build_default_registry()
    monkeypatch.setattr(planner_mod, "gateway", LLMGateway(FakeBackend(
        [{"name": "remember", "args": {"key": "gym_membership", "value": "unused"}}])))
    plan = LLMPlanner(reg, RulePlanner(reg)).plan("remember unused_subscriptions: California Fitness", ctx(), {})
    assert plan.intent == "remember" and plan.calls[0].args == {"key": "unused_subscriptions", "value": "California Fitness"}
