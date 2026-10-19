"""Runs preflight-approved calls, never raises, records timing and fallback markers."""
import time
from typing import List

from app.agent.tools import ToolRegistry
from app.agent.types import AgentContext, PlannedCall, PreflightDecision, ToolResult
from app.core.notifications import notifications

MONEY_TOOLS = {"transfer_internal", "transfer_external", "cancel_subscription", "set_budget"}
_DONE = ("EXECUTED", "SET", "FLAGGED_FOR_CANCELLATION")


class Executor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def _notify(self, call: PlannedCall, out: dict, ctx: AgentContext, human_approved: bool) -> None:
        """Tell the user about every state-changing action, the moment it happens."""
        if call.tool not in MONEY_TOOLS or not str(out.get("status", "")).upper().startswith(_DONE):
            return
        tier = self.registry.get(call.tool).tier(call.args, ctx)
        what = out.get("message") or f"{call.tool} {out.get('status')}"
        if human_approved:
            notifications.push("Approved action carried out", what, tier, kind="approved")
        else:
            notifications.push("SpendGuard acted on its own (Tier 2)", what, tier, kind="auto")

    def run_one(self, call: PlannedCall, ctx: AgentContext, human_approved: bool = False) -> ToolResult:
        args = dict(call.args)
        if call.tool in MONEY_TOOLS:
            args["human_approved"] = human_approved
        start = time.perf_counter()
        try:
            out = self.registry.get(call.tool).handler(args, ctx)
            if not isinstance(out, dict):
                out = {"value": out}
            fallback = bool(out.get("fallback")) or "fallback" in str(out.get("source", "")).lower()
            try:
                self._notify(call, out, ctx, human_approved)
            except Exception:
                pass                                     # a failed notice must never turn an executed action into an error
            return ToolResult(call.tool, call.args, out, int((time.perf_counter() - start) * 1000), None, fallback)
        except Exception as ex:
            return ToolResult(call.tool, call.args, {}, int((time.perf_counter() - start) * 1000), f"{type(ex).__name__}: {ex}")

    def run(self, decisions: List[PreflightDecision], ctx: AgentContext) -> List[ToolResult]:
        return [self.run_one(d.call, ctx) for d in decisions if d.verdict == "EXECUTE"]
