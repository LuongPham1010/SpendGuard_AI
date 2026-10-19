"""
Audit Logger: Sandbox Execution Trace & Compliance Evidence
Shenzhen International FinTech Competition 2026 - Deliverable 06 Compliance
"""

import json
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path
from app.config import EXECUTION_LOG_FILE
from app.models.schemas import AuditLogEntry

# A bare run of 9-16 digits in a log string is treated as an account or card number (amounts are logged as numbers)
_ACCOUNT_RUN = re.compile(r"(?<!\d)(\d{3})(\d{3,10})(\d{3})(?!\d)")


def _mask_text(s: str) -> str:
    return _ACCOUNT_RUN.sub(lambda m: m.group(1) + "*" * len(m.group(2)) + m.group(3), s)


def _mask_details(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, dict):
        return {k: _mask_details(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask_details(v) for v in value]
    return value


class SandboxAuditLogger:
    """Tamper-evident Sandbox Execution Logger with chained SHA256 hashes"""

    _last_hash: str = "GENESIS_ROOT_SPENDGUARD_2026"
    _in_memory_logs: List[AuditLogEntry] = []

    @classmethod
    def log_event(
        cls,
        tier: str,
        module: str,
        action: str,
        status: str,
        details: Dict[str, Any],
    ) -> AuditLogEntry:
        """Log a financial or agentic action to sandbox log file and memory.
        Account-like digit runs are masked and a transfer signature is stored only as a digest, so neither the
        file nor the in-memory ledger keeps a full account number."""
        raw = dict(details or {})
        details = _mask_details(raw)
        if isinstance(raw.get("signature"), str):            # digest of the unmasked signature, set after masking
            details["signature"] = cls.signature_digest(raw["signature"])
        timestamp = datetime.now(timezone.utc).isoformat()
        entry_id = str(uuid.uuid4())[:12]

        # Compute chained hash for integrity audit
        payload = f"{cls._last_hash}|{timestamp}|{tier}|{module}|{action}|{status}|{json.dumps(details, sort_keys=True)}"
        current_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        cls._last_hash = current_hash

        entry = AuditLogEntry(
            id=entry_id,
            timestamp=timestamp,
            tier=tier,
            module=module,
            action=action,
            status=status,
            details=details,
            trace_hash=current_hash,
        )

        cls._in_memory_logs.append(entry)

        # Append to log file
        try:
            EXECUTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EXECUTION_LOG_FILE, "a", encoding="utf-8") as f:
                log_line = f"[{timestamp}] [{tier}] [{module}] [{action}] [{status}] HASH={current_hash} DETAILS={json.dumps(details, ensure_ascii=False)}\n"
                f.write(log_line)
        except Exception as e:
            print(f"[AuditLogger Warning] Could not write to log file: {e}")

        return entry

    @staticmethod
    def signature_digest(signature: str) -> str:
        """Stable digest of a transfer signature; duplicate detection compares digests, never raw accounts."""
        if signature.startswith("sig:"):
            return signature
        return "sig:" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def get_recent_logs(cls, limit: int = 50) -> List[AuditLogEntry]:
        """Return the most recent audit entries"""
        return list(reversed(cls._in_memory_logs[-limit:]))

    @classmethod
    def get_raw_log_lines(cls, limit: int = 100) -> List[str]:
        """Read recent lines directly from the log file"""
        if not EXECUTION_LOG_FILE.exists():
            return []
        try:
            with open(EXECUTION_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return lines[-limit:]
        except Exception:
            return []
