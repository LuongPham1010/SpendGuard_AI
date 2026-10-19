from evals.run_evals import run_all, load_jsonl


def test_corpus_size_and_balance():
    rows = load_jsonl("evals/tasks/guardian_corpus.jsonl")
    assert len(rows) >= 100
    scam = sum(r["label"] == "scam" for r in rows)
    assert 0.4 <= scam / len(rows) <= 0.6
    assert len({r["scam_type"] for r in rows if r["label"] == "scam"}) >= 6


def test_run_all_writes_report_and_meets_floor(tmp_path):
    rep = run_all(out_dir=str(tmp_path))
    assert (tmp_path / "report.json").exists() and (tmp_path / "report.md").exists()
    assert rep["functional"]["pass_rate"] >= 0.9
    assert rep["guardian"]["f1"] >= 0.85
    assert rep["adversarial"]["block_rate"] == 1.0


def test_adversarial_blocks_come_from_the_injection_downgrade_not_duplicates(tmp_path):
    rep = run_all(out_dir=str(tmp_path))
    for d in rep["adversarial"]["details"]:
        assert "REJECT" not in d["verdicts"].values(), d


def test_unseen_suite_exists_and_is_reported(tmp_path):
    rows = load_jsonl("evals/tasks/guardian_unseen.jsonl")
    assert len(rows) >= 30 and {r["label"] for r in rows} == {"scam", "legit"}
    rep = run_all(out_dir=str(tmp_path))
    u = rep["guardian_unseen"]
    assert set(u) >= {"lock_precision", "lock_recall", "lock_f1", "escalation_recall_with_cue", "confusion", "text_only", "velocity_1"}
    assert 0.0 <= u["lock_f1"] <= 1.0
