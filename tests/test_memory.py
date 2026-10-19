from app.agent.memory import ProfileStore, SessionMemory, UserProfile


def test_profile_roundtrip(tmp_path):
    store = ProfileStore(tmp_path / "p.json")
    p = store.load()
    assert isinstance(p, UserProfile) and p.monthly_income == 35_000_000
    p.facts["goal"] = "save for a motorbike"
    store.save(p)
    assert ProfileStore(tmp_path / "p.json").load().facts["goal"] == "save for a motorbike"


def test_new_payee_detection(tmp_path):
    store = ProfileStore(tmp_path / "p.json")
    p = store.load()
    assert store.is_new_payee(p, "0123456789") is True
    store.record_payee(p, "Nguyen Van A", "0123456789")
    assert store.is_new_payee(p, "0123456789") is False
    assert p.known_payees["0123456789"].account_masked == "012****789"


def test_session_memory_keeps_last_n():
    mem = SessionMemory()
    for i in range(7):
        mem.add_turn("s", {"i": i})
    assert [t["i"] for t in mem.history("s", n=5)] == [2, 3, 4, 5, 6]
