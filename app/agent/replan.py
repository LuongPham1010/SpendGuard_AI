"""One replanning round after the first tool results: deterministic rules always, model proposals when available.
Replans may only add read-only tools; money and settings changes never come from a replan."""
from typing import List

from app.agent.tools import ToolRegistry
from app.agent.types import AgentContext, PlannedCall, ToolResult
from app.core.llm_gateway import gateway, Part

READ_ONLY_REPLAN_TOOLS = {"get_budget_status", "scan_subscriptions", "run_stress_test", "get_wallets",
                          "get_transactions", "explain_transaction", "check_payee", "recall"}
MAX_REPLAN_CALLS = 2


def _out(results: List[ToolResult], tool: str) -> dict:
    return next((r.output for r in results if r.tool == tool and r.error is None), {})


def rule_replan(intent: str, results: List[ToolResult], ctx: AgentContext) -> List[PlannedCall]:
    """Deterministic follow-ups a careful assistant would make."""
    extra: List[PlannedCall] = []
    done = {r.tool for r in results}
    if intent == "budget_status":
        b = _out(results, "get_budget_status").get("breakdown", {})
        if b.get("Wants", {}).get("status") == "OVER_BUDGET" and "scan_subscriptions" not in done:
            extra.append(PlannedCall("scan_subscriptions", {}, "Wants are over budget; recurring fees are the usual cause"))
    if intent == "stress_test":
        o = _out(results, "run_stress_test")
        if o and o.get("resilience_score", 100) < 50 and "get_budget_status" not in done:
            extra.append(PlannedCall("get_budget_status", {}, "low resilience; show where the savings gap is"))
    if intent == "transfer_external":
        g = _out(results, "guardian_scan")
        if g and g.get("features", {}).get("payee_is_new") == 1.0 and "check_payee" not in done:
            acct = next((r.args.get("payee_account") for r in results if r.tool == "guardian_scan"), "")
            if acct:
                extra.append(PlannedCall("check_payee", {"account": acct}, "first-time payee; consult the warning list"))
    return extra[:MAX_REPLAN_CALLS]


def llm_replan(intent: str, text: str, results: List[ToolResult], ctx: AgentContext, registry: ToolRegistry) -> List[PlannedCall]:
    """Ask the model whether read-only follow-ups would help; every proposal is validated and capped."""
    if not gateway.available or not results:
        return []
    decls = [d for d in registry.function_declarations() if d["name"] in READ_ONLY_REPLAN_TOOLS]
    res = gateway.generate(
        f"The user asked: {text}. Tool results so far are in the data block. "
        "If one or two more read-only tools would materially improve the answer, call them; otherwise call nothing.",
        instructions="You are SpendGuard's planner doing a single replanning round. Only read-only tools are offered.",
        untrusted=[Part(kind="text", content=str([{"tool": r.tool, "output": r.output} for r in results]), source="tool_results", trusted=True)],
        tools=decls, purpose="replan")
    calls = []
    for fc in res.function_calls[:MAX_REPLAN_CALLS]:
        c = PlannedCall(fc["name"], dict(fc.get("args", {})), "model replan")
        if c.tool in READ_ONLY_REPLAN_TOOLS and not registry.validate(c):
            calls.append(c)
    return calls


def replan(intent: str, text: str, results: List[ToolResult], ctx: AgentContext, registry: ToolRegistry) -> List[PlannedCall]:
    extra = rule_replan(intent, results, ctx)
    if not extra:
        extra = llm_replan(intent, text, results, ctx, registry)
    done = {r.tool for r in results}
    return [c for c in extra if c.tool not in done][:MAX_REPLAN_CALLS]
