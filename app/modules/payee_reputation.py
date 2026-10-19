"""Payee reputation: is this account number on a scam warning list?

Providers are pluggable. The default is a local, team-curated blocklist assembled from public warnings
(NCSC lookup at tinnhiemmang.vn, canhbao.ncsc.gov.vn, police bulletins). An optional HTTP provider can be
configured with PAYEE_LOOKUP_URL containing "{account}"; it must return JSON with a "status" field.
No official public API exists for Vietnamese scam-account lookups as of 2026-10, so the HTTP provider is a hook.
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import BASE_DIR

DEFAULT_BLOCKLIST = BASE_DIR / "data" / "guardian" / "payee_blocklist.json"


def _norm_account(account: str) -> str:
    return re.sub(r"\D", "", account or "")


class LocalBlocklist:
    name = "local_blocklist"

    def __init__(self, path: Path = DEFAULT_BLOCKLIST):
        self.path = Path(path)
        self._entries: Optional[List[dict]] = None

    def _load(self) -> List[dict]:
        if self._entries is None:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                entries = raw.get("entries") if isinstance(raw, dict) else None
            except Exception:
                entries = None
            clean = []
            for e in entries or []:
                if isinstance(e, dict) and isinstance(e.get("account"), str) and _norm_account(e["account"]):
                    clean.append(e)
            self._entries = clean
        return self._entries

    def lookup(self, account: str, bank: str = "") -> Optional[Dict[str, Any]]:
        acc = _norm_account(account)
        if not acc:
            return None
        for e in self._load():
            if _norm_account(e.get("account", "")) == acc and (not e.get("bank") or not bank or e["bank"].lower() == bank.lower()):
                return {"status": "blacklisted", "label": e.get("label", "reported"), "source": e.get("source", ""),
                        "provider": self.name, "added": e.get("added", "")}
        return None


class HttpProvider:
    name = "http_lookup"

    def __init__(self, url_template: str, timeout: float = 3.0):
        self.url_template = url_template
        self.timeout = timeout

    def lookup(self, account: str, bank: str = "") -> Optional[Dict[str, Any]]:
        acc = _norm_account(account)
        if not acc or "{account}" not in self.url_template:
            return None
        try:
            import requests
            r = requests.get(self.url_template.format(account=acc), timeout=self.timeout)
            data = r.json() if r.ok else {}
            status = str(data.get("status", "")).lower()
            if status in ("blacklisted", "scam", "fraud"):
                return {"status": "blacklisted", "label": data.get("label", "reported"), "source": self.url_template.split("{")[0],
                        "provider": self.name, "added": data.get("added", "")}
            if status in ("clean", "safe"):
                return {"status": "clean", "label": "", "source": self.url_template.split("{")[0], "provider": self.name, "added": ""}
        except Exception:
            return None
        return None


class PayeeReputation:
    def __init__(self, providers: Optional[list] = None):
        self.providers = providers if providers is not None else self._default_providers()
        self._cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _default_providers() -> list:
        providers: list = [LocalBlocklist()]
        url = os.getenv("PAYEE_LOOKUP_URL", "")
        if url:
            providers.append(HttpProvider(url))
        return providers

    def lookup(self, account: str, bank: str = "") -> Dict[str, Any]:
        key = f"{_norm_account(account)}|{(bank or '').lower()}"
        if key in self._cache:
            return self._cache[key]
        result: Dict[str, Any] = {"status": "unknown", "label": "", "source": "", "provider": "", "added": ""}
        for p in self.providers:
            hit = p.lookup(account, bank)
            if hit and hit["status"] == "blacklisted":
                result = hit
                break
            if hit and hit["status"] == "clean" and result["status"] == "unknown":
                result = hit
        self._cache[key] = result
        return result


payee_reputation = PayeeReputation()
