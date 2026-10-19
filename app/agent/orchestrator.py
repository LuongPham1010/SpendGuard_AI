"""State-machine orchestrator: INTAKE -> GUARDRAIL -> PLAN -> PREFLIGHT -> EXECUTE | AWAIT_HUMAN -> REFLECT -> RESPOND."""
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List
from pydantic import BaseModel, Field

from app.agent.approvals import ApprovalQueue, approval_queue
from app.agent.executor import Executor
import app.agent.memory as memory_mod
from app.agent.memory import session_memory
from app.agent.planner import make_planner
from app.agent.preflight import Preflight
from app.agent.reflect import Reflector, render_template
from app.agent.replan import replan
from app.agent.tools import ToolRegistry, build_default_registry
from app.agent.types import AgentContext, Phase, Plan, PreflightDecision, ToolResult
from app.config import CIRCUIT_BREAKER_ERRORS, MAX_ITERATIONS, PLANNER_MAX_CALLS
from app.core.audit_logger import SandboxAuditLogger
from app.core.llm_gateway import gateway, Part
from app.core.security import SecurityGuard


class AgentTurn(BaseModel):
    session_id: str
    input: str
    intent: str = "unknown"
    plan: List[dict] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    decisions: List[dict] = Field(default_factory=list)
    results: List[dict] = Field(default_factory=list)
    queued: List[dict] = Field(default_factory=list)
    reflect: dict = Field(default_factory=dict)
    response: str = ""
    trace: List[dict] = Field(default_factory=list)


class Orchestrator:
    def __init__(self, registry: ToolRegistry, planner, preflight: Preflight, executor: Executor, queue: ApprovalQueue):
        self.registry = registry
        self.planner = planner
        self.preflight = preflight
        self.executor = executor
        self.queue = queue

    @staticmethod
    def _mark(turn: AgentTurn, phase: Phase, detail: str = ""):
        turn.trace.append({"phase": phase.value, "at": datetime.now(timezone.utc).isoformat(), "detail": detail})

    def run_turn(self, session_id: str, text: str, attachments: Dict[str, bytes], transactions: list) -> AgentTurn:
        turn = AgentTurn(session_id=session_id, input=text)
        history = session_memory.get_recent(session_id) if hasattr(session_memory, "get_recent") else getattr(session_memory, "_turns", {}).get(session_id, [])

        # INTAKE
        self._mark(turn, Phase.INTAKE, f"{len(transactions)} transactions, {len(attachments)} attachments")
        ctx = AgentContext(session_id=session_id, transactions=transactions, profile=memory_mod.profile_store.load(),
                           flags=[], images=dict(attachments))

        # GUARDRAIL
        hits = SecurityGuard.scan_injection(text)
        for t in transactions[:500]:
            if SecurityGuard.scan_injection(getattr(t, "description", "") or ""):
                hits.append("csv:" + str(getattr(t, "id", "?")))
        if hits:
            ctx.flags.append("INJECTION_SUSPECTED")
        turn.flags = list(ctx.flags)
        self._mark(turn, Phase.GUARDRAIL, f"injection hits: {len(hits)}")

        # PLAN (Truyền thêm history để hiểu ngữ cảnh đa vòng, tương thích ngược nếu planner cũ không nhận history)
        try:
            plan: Plan = self.planner.plan(text, ctx, attachments, history=history)
        except TypeError:
            plan = self.planner.plan(text, ctx, attachments)

        if plan.intent == "run_my_month":
            from app.agent.playbooks import expand_run_my_month
            plan = expand_run_my_month(ctx)
        plan.calls = plan.calls[:PLANNER_MAX_CALLS]
        for call in plan.calls:                      # Guardian always sees the user's own words, whatever the planner wrote
            if call.tool in ("guardian_scan", "transfer_external", "transfer_internal"):
                prev = call.args.get("evidence_text", "") or ""
                if text not in prev:
                    call.args["evidence_text"] = (prev + "\n" + text).strip()
        turn.intent = plan.intent
        turn.plan = [asdict(c) for c in plan.calls]
        self._mark(turn, Phase.PLAN, f"{plan.intent} via {plan.source}: {[c.tool for c in plan.calls]}")

        # PREFLIGHT + EXECUTE (Giữ nguyên 100% tuần tự và nghiêm ngặt theo chuẩn kiểm toán ngân hàng)
        decisions: List[PreflightDecision] = []
        results: List[ToolResult] = []
        guardian_results: Dict[int, dict] = {}
        consecutive_errors = 0
        iterations = 1
        for idx, call in enumerate(plan.calls):
            if consecutive_errors >= CIRCUIT_BREAKER_ERRORS:
                # circuit breaker: after repeated tool failures the rest of the plan is not attempted
                decisions.append(PreflightDecision(call, "Tier 1", "REJECT",
                                                   [f"circuit breaker open after {CIRCUIT_BREAKER_ERRORS} consecutive tool errors"]))
                continue
            supplied = {0: guardian_results[idx]} if idx in guardian_results else None
            d = self.preflight.check([call], ctx, supplied)[0]
            decisions.append(d)
            if d.verdict != "EXECUTE":
                continue
            r = self.executor.run_one(call, ctx)
            results.append(r)
            consecutive_errors = consecutive_errors + 1 if r.error else 0
            if consecutive_errors == CIRCUIT_BREAKER_ERRORS and "CIRCUIT_OPEN" not in ctx.flags:
                ctx.flags.append("CIRCUIT_OPEN")
                SandboxAuditLogger.log_event(tier="Tier 1", module="Orchestrator", action="CIRCUIT_OPEN", status="HALTED",
                                             details={"session": session_id, "after_tool": call.tool,
                                                      "remaining_calls": len(plan.calls) - idx - 1})
            if call.tool == "guardian_scan" and r.error is None:
                for j in range(idx + 1, len(plan.calls)):
                    if plan.calls[j].tool in ("transfer_external", "transfer_internal"):
                        guardian_results[j] = r.output
                        break
            if call.tool == "read_chat_screenshot" and r.error is None and r.output.get("text"):
                if SecurityGuard.scan_injection(r.output["text"]) and "INJECTION_SUSPECTED" not in ctx.flags:
                    ctx.flags.append("INJECTION_SUSPECTED")
                for j in range(idx + 1, len(plan.calls)):
                    if plan.calls[j].tool in ("guardian_scan", "transfer_external", "transfer_internal"):
                        prev = plan.calls[j].args.get("evidence_text", "")
                        plan.calls[j].args["evidence_text"] = (prev + "\n" + r.output["text"]).strip()
                for f in r.output.get("flags", []):
                    if f not in ctx.flags:
                        ctx.flags.append(f)
        self._mark(turn, Phase.PREFLIGHT, str([d.verdict for d in decisions]))
        self._mark(turn, Phase.EXECUTE, f"{len(results)} calls run")

        # REPLAN: one round of read-only follow-ups based on what the tools returned (never after the breaker opened)
        if (results and plan.intent not in ("run_my_month", "unknown") and "CIRCUIT_OPEN" not in ctx.flags
                and iterations < MAX_ITERATIONS):
            iterations += 1
            extra = replan(plan.intent, text, results, ctx, self.registry)
            if extra:
                for call in extra:
                    d = self.preflight.check([call], ctx)[0]
                    decisions.append(d)
                    if d.verdict == "EXECUTE":
                        results.append(self.executor.run_one(call, ctx))
                plan.calls.extend(extra)
                turn.plan = [asdict(c) for c in plan.calls]
                self._mark(turn, Phase.REPLAN, f"added {[c.tool for c in extra]}")

        # AWAIT_HUMAN
        queued = [self.queue.enqueue(session_id, d) for d in decisions if d.verdict in ("AWAIT_HUMAN", "LOCKED")]
        if queued:
            self._mark(turn, Phase.AWAIT_HUMAN, f"{len(queued)} requests queued")

        # REFLECT
        template_text = render_template(plan.intent, plan, results, decisions, queued)
        narrative = template_text
        has_rejections = any(getattr(d, "verdict", "") == "REJECT" for d in decisions)
        if gateway.available and results and not has_rejections:
            # The model must know what is frozen or waiting, or it may tell the user nothing is pending
            status = [{"tool": d.call.tool, "amount": d.call.args.get("amount"), "verdict": d.verdict} for d in decisions
                      if d.call.tool in ("transfer_internal", "transfer_external", "cancel_subscription", "set_budget")]
            res = gateway.generate("Write a short, plain answer for the user using only the numbers in the data.",
                                   instructions="You are SpendGuard's assistant. Max 6 sentences. Answer in the language of the "
                                                "user_request (Vietnamese or English). Format money as 1,234,567 VND and "
                                                "percentages as 12.5%; a Guardian risk score is out of 100, written like 69.4/100. "
                                                "action_status lists each money action: LOCKED means frozen by Guardian, "
                                                "AWAIT_HUMAN means waiting for the user's approval with a one-time code, EXECUTE "
                                                "means already done. Say this in plain words and never print the codes "
                                                "themselves; mention counter-facts when present.",
                                   untrusted=[Part(kind="text", content=text, source="user_request"),
                                              Part(kind="text", content=str([r.output for r in results]),
                                                   source="tool_results", trusted=True),
                                              Part(kind="text", content=str(status), source="action_status", trusted=True)],
                                   purpose="narrative")
            if res.available and res.text.strip():
                narrative = res.text.strip()
        text_out, rep = Reflector.finalize(narrative, plan.intent, plan, results, decisions, queued)
        turn.reflect = {"grounded": rep.grounded, "unmatched": rep.unmatched, "regenerated": rep.regenerated}
        self._mark(turn, Phase.REFLECT, f"grounded={rep.grounded} regenerated={rep.regenerated}")

        # RESPOND
        turn.decisions = [{"call": asdict(d.call), "tier": d.tier, "verdict": d.verdict, "reasons": d.reasons,
                           "guardian": d.guardian} for d in decisions]
        turn.results = [asdict(r) for r in results]
        turn.queued = [q.model_dump() for q in queued]
        turn.response = text_out
        turn.flags = list(ctx.flags)
        self._mark(turn, Phase.RESPOND, "")
        session_memory.add_turn(session_id, {"input": text, "intent": plan.intent, "response": text_out})
        SandboxAuditLogger.log_event(tier="Tier 1", module="Orchestrator", action="TURN_COMPLETED", status="OK",
                                     details={"session": session_id, "intent": plan.intent, "executed": len(results),
                                              "queued": len(queued), "grounded": rep.grounded, "flags": ctx.flags})
        return turn


def build_agent() -> Orchestrator:
    registry = build_default_registry()
    return Orchestrator(registry, make_planner(registry), Preflight(registry), Executor(registry), approval_queue)


agent = build_agent()
