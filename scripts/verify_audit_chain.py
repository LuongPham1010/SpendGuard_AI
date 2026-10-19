"""Recompute the SHA-256 chain of a SpendGuard audit log and report the first broken line, if any.

Each line is: [timestamp] [tier] [module] [action] [status] HASH=<16 hex> DETAILS=<json>
hash_n = sha256(hash_{n-1} | timestamp | tier | module | action | status | json(details, sort_keys)) [:16],
starting from the genesis value used by app/core/audit_logger.py.

Usage: python scripts/verify_audit_chain.py [path/to/log]
"""
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Tuple

GENESIS = "GENESIS_ROOT_SPENDGUARD_2026"
LINE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[(?P<tier>[^\]]+)\] \[(?P<module>[^\]]+)\] \[(?P<action>[^\]]+)\] "
                  r"\[(?P<status>[^\]]*)\] HASH=(?P<hash>[0-9a-f]{16}) DETAILS=(?P<details>.*)$")


def verify(path: Path) -> Tuple[bool, int, str]:
    prev = GENESIS
    count = 0
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        m = LINE.match(raw)
        if not m:
            return False, count, f"line {n}: unreadable entry"
        details = json.loads(m["details"])
        payload = f"{prev}|{m['ts']}|{m['tier']}|{m['module']}|{m['action']}|{m['status']}|{json.dumps(details, sort_keys=True)}"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        if expected != m["hash"]:
            return False, count, f"line {n}: hash mismatch (expected {expected}, found {m['hash']})"
        prev = m["hash"]
        count += 1
    return True, count, f"chain valid: {count} entries, head {prev}"


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "evidence/sandbox_execution_evidence.log")
    ok, _, message = verify(target)
    print(message)
    sys.exit(0 if ok else 1)
