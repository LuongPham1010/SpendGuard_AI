from app.agent.preflight import Preflight
from app.agent.tools import build_default_registry
from app.agent.types import AgentContext, PlannedCall
from app.agent.memory import UserProfile
from app.core.sandbox_wallets import wallet_manager


def ctx(flags=None):
    return AgentContext(session_id="t", transactions=[], profile=UserProfile(), flags=flags or [])


def test_read_only_executes():
    d = Preflight(build_default_registry()).check([PlannedCall("get_wallets", {})], ctx())[0]
    assert d.verdict == "EXECUTE" and d.tier == "Tier 1"


def test_small_internal_transfer_executes_large_awaits_human():
    pf = Preflight(build_default_registry())
    small = PlannedCall("transfer_internal", {"source": "Main Wallet", "destination": "Emergency Vault", "amount": 1_000_000})
    big = PlannedCall("transfer_internal", {"source": "Main Wallet", "destination": "Emergency Vault", "amount": 9_000_000})
    ds = pf.check([small, big], ctx())
    assert ds[0].verdict == "EXECUTE" and ds[1].verdict == "AWAIT_HUMAN"


def test_insufficient_funds_rejected():
    d = Preflight(build_default_registry()).check(
        [PlannedCall("transfer_internal", {"source": "Fun Wallet", "destination": "Main Wallet", "amount": 999_000_000})], ctx())[0]
    assert d.verdict == "REJECT" and any("dry-run" in r for r in d.reasons)


def test_external_transfer_with_scam_evidence_is_locked():
    call = PlannedCall("transfer_external", {"payee_name": "Cong an", "payee_account": "0123456789", "amount": 50_000_000,
                                             "note": "tai khoan tam giu", "evidence_text": "cong an dieu tra, chuyen gap, giu bi mat"})
    d = Preflight(build_default_registry()).check([call], ctx())[0]
    assert d.verdict == "LOCKED" and d.guardian["locked"] is True


def test_innocent_note_but_vault_drain_still_reaches_guardian():
    vault = wallet_manager.get_wallet("emergency").balance
    call = PlannedCall("transfer_internal", {"source": "Emergency Vault", "destination": "Fun Wallet",
                                             "amount": round(vault * 0.8), "note": "holiday"})
    d = Preflight(build_default_registry()).check([call], ctx())[0]
    assert d.guardian is not None and d.verdict in ("AWAIT_HUMAN", "LOCKED")


def test_injection_flag_downgrades_tier2_to_await_human():
    from app.modules.data_ingestion import DataIngestionEngine
    call = PlannedCall("cancel_subscription", {"merchant": "Netflix"})
    c = ctx(flags=["INJECTION_SUSPECTED"])
    c.transactions = DataIngestionEngine.load_default_transactions()   # the dry-run needs Netflix on the statement
    d = Preflight(build_default_registry()).check([call], c)[0]
    assert d.verdict == "AWAIT_HUMAN" and any("injection" in r.lower() for r in d.reasons)


def test_unknown_tool_rejected():
    d = Preflight(build_default_registry()).check([PlannedCall("explode", {})], ctx())[0]
    assert d.verdict == "REJECT"
