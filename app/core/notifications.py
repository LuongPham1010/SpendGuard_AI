"""User notifications for actions the agent took on its own (Tier 2) or after an approval.
The sandbox has no push service: notifications are kept in memory, shown by the web UI and labelled [simulated push]."""
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.audit_logger import SandboxAuditLogger


class NotificationCenter:
    def __init__(self, keep: int = 100):
        self._items: List[Dict[str, Any]] = []
        self._next_id = 1
        self._keep = keep

    def push(self, title: str, body: str, tier: str, kind: str = "auto") -> Dict[str, Any]:
        item = {"id": self._next_id, "at": datetime.now(timezone.utc).isoformat(), "title": title, "body": body,
                "tier": tier, "kind": kind, "channel": "simulated push", "read": False}
        self._next_id += 1
        self._items.append(item)
        self._items = self._items[-self._keep:]
        SandboxAuditLogger.log_event(tier=tier, module="Notifications", action="PUSH_SENT", status="SIMULATED",
                                     details={"notification_id": item["id"], "title": title, "kind": kind})
        return item

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(reversed(self._items[-limit:]))

    def unread(self) -> int:
        return sum(1 for n in self._items if not n["read"])

    def mark_all_read(self) -> None:
        for n in self._items:
            n["read"] = True

    def clear(self) -> None:
        self._items = []


notifications = NotificationCenter()
