"""Shared agent data types: phases, plans, preflight decisions, tool results, context."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Phase(str, Enum):
    INTAKE = "INTAKE"
    GUARDRAIL = "GUARDRAIL"
    PLAN = "PLAN"
    PREFLIGHT = "PREFLIGHT"
    EXECUTE = "EXECUTE"
    REPLAN = "REPLAN"
    AWAIT_HUMAN = "AWAIT_HUMAN"
    REFLECT = "REFLECT"
    RESPOND = "RESPOND"
    DONE = "DONE"


@dataclass
class PlannedCall:
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class Plan:
    intent: str
    calls: List[PlannedCall]
    source: str = "rule"


@dataclass
class PreflightDecision:
    call: PlannedCall
    tier: str
    verdict: str              # EXECUTE | AWAIT_HUMAN | LOCKED | REJECT
    reasons: List[str] = field(default_factory=list)
    guardian: Optional[Dict[str, Any]] = None


@dataclass
class ToolResult:
    tool: str
    args: Dict[str, Any]
    output: Dict[str, Any]
    duration_ms: int = 0
    error: Optional[str] = None
    fallback: bool = False


@dataclass
class AgentContext:
    session_id: str
    transactions: List[Any]
    profile: Any
    flags: List[str] = field(default_factory=list)
    images: Dict[str, bytes] = field(default_factory=dict)   # attachment id -> bytes
