import json
from pathlib import Path
from app.agent.types import AgentContext
from app.agent.memory import UserProfile
from app.modules.guardian import Guardian, TransferIntent, Evidence


def ctx():
    return AgentContext(session_id="t", transactions=[], profile=UserProfile(), flags=[])


def test_rule_features_match_accented_and_unaccented_vietnamese():
    f1 = Guardian.rule_features("Tôi là công an, chuyển gấp vào tài khoản an toàn, giữ bí mật")
    f2 = Guardian.rule_features("toi la cong an, chuyen gap vao tai khoan an toan, giu bi mat")
    for k in ("authority_impersonation", "urgency", "secrecy", "safe_account"):
        assert f1[k] == 1.0 and f2[k] == 1.0


def test_ponzi_math_feature_reads_daily_yield():
    f = Guardian.rule_features("lãi 3% mỗi ngày, cam kết lợi nhuận")
    assert f["ponzi_math"] == 3.0


def test_behavior_features_new_payee_and_vault_drain():
    intent = TransferIntent(amount=100_000_000, payee_account="0123456789")
    f = Guardian.behavior_features(intent, ctx())
    assert f["payee_is_new"] == 1.0
    assert f["drains_vault"] > 0.2


def test_police_impersonation_is_locked_with_counter_facts():
    intent = TransferIntent(amount=50_000_000, payee_name="Cong an TP", payee_account="0123456789", bank="vietcombank")
    ev = Evidence(text="Đây là cơ quan công an, anh đang bị điều tra rửa tiền, chuyển ngay vào tài khoản tạm giữ, không nói với ai")
    r = Guardian.assess(intent, ev, ctx())
    assert r.locked is True and r.level == "CRITICAL"
    assert r.scam_type == "authority_impersonation"
    assert any("never" in c.lower() for c in r.counter_facts)
    assert len(r.quiz) == 3


def test_legit_rent_transfer_with_urgent_word_is_not_locked():
    intent = TransferIntent(amount=8_500_000, payee_name="Landlord", payee_account="5555555555", bank="techcombank")
    ev = Evidence(text="Rent for October, landlord asked to pay urgently today, same account as every month")
    c = ctx()
    c.profile.known_payees["5555555555"] = {"name": "Landlord", "account_masked": "555****555", "first_seen": "2026-01-01", "count": 9}
    r = Guardian.assess(intent, ev, c)
    assert r.locked is False and r.risk_score < 50


def test_weights_file_is_valid():
    w = json.loads(Path("app/modules/guardian_weights.json").read_text())
    assert set(w) == {"weights", "bias", "threshold"} and 0 < w["threshold"] <= 100


def test_behavioral_signals_alone_do_not_lock():
    """A new payee and a large round amount with no scam content escalate to human approval, never to a lock."""
    intent = TransferIntent(amount=20_000_000, payee_name="Sister", payee_account="999888777", bank="techcombank")
    r = Guardian.assess(intent, Evidence(text="send 20 million for my sister's tuition"), ctx())
    assert r.locked is False
    assert all(r.features[k] == 0.0 for k in ("authority_impersonation", "urgency", "secrecy", "safe_account", "ponzi_math"))
