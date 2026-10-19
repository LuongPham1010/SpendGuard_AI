"""Shared test isolation: the audit log keeps an in-memory list that duplicate detection reads,
and the sandbox wallets are a process-wide singleton."""
import os
os.environ["LLM_PROVIDER"] = "none"   # tests never call a model; set before app.config is imported
os.environ["DEMO_ACCESS_TOKEN"] = ""  # tests run the API without the public-demo gate, whatever .env says
import pytest
from app.core.audit_logger import SandboxAuditLogger
from app.core.sandbox_wallets import wallet_manager

_INITIAL_BALANCES = {"main": 65_000_000.0, "emergency": 120_000_000.0, "fun": 15_000_000.0}


@pytest.fixture(autouse=True)
def _reset_shared_state(tmp_path, monkeypatch):
    import app.agent.memory as memory_mod
    import app.agent.approvals as approvals_mod
    from app.agent.memory import ProfileStore
    store = ProfileStore(tmp_path / "profile.json")        # tests never touch data/memory/profile.json
    monkeypatch.setattr(memory_mod, "profile_store", store)
    monkeypatch.setattr(approvals_mod, "profile_store", store)
    SandboxAuditLogger._in_memory_logs.clear()
    for wid, bal in _INITIAL_BALANCES.items():
        wallet_manager.get_wallet(wid).balance = bal
    yield
