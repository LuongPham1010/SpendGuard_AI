"""Fit Guardian fusion weights and threshold on the labeled corpus (deterministic coordinate descent)."""
import json
import math
import random
from pathlib import Path

from app.agent.types import AgentContext
from app.agent.memory import UserProfile
from app.core.security import SecurityGuard
from app.modules.guardian import Guardian, TransferIntent, WEIGHTS_PATH

from evals.run_evals import load_jsonl, KNOWN_PAYEE

URGENT = ("gap", "urgent", "ngay hom nay", "today", "han cuoi")


def _features(row):
    ctx = AgentContext("fit", [], UserProfile(), [])
    if not row["payee_new"]:
        ctx.profile.known_payees["ACC"] = KNOWN_PAYEE
    f = Guardian.rule_features(row["text"])
    f.update(Guardian.behavior_features(
        TransferIntent(amount=row["amount"], payee_account=row.get("payee_account") or ("ACC" if not row["payee_new"] else "NEW123456789")), ctx))
    f["llm_confidence"] = 0.0
    return f


def _score(cfg, f):
    z = cfg["bias"]
    for k, w in cfg["weights"].items():
        v = f.get(k, 0.0)
        if k == "ponzi_math":
            v = min(v, 5.0)
        z += w * v
    return 100.0 / (1.0 + math.exp(-z))


def _metrics(cfg, rows, feats):
    tp = fp = fn = 0
    pen = 0
    for r, f in zip(rows, feats):
        pred = _score(cfg, f) >= cfg["threshold"] and Guardian.has_content_cue(f)   # same lock rule as the deployed Guardian
        if r["label"] == "scam":
            if pred:
                tp += 1
            else:
                fn += 1
        elif pred:
            fp += 1
            if any(u in SecurityGuard.normalize_text(r["text"]) for u in URGENT):
                pen += 2
    p = tp / max(tp + fp, 1)
    rc = tp / max(tp + fn, 1)
    f1 = 2 * p * rc / max(p + rc, 1e-9)
    return {"precision": round(p, 3), "recall": round(rc, 3), "f1": round(f1, 3), "objective": f1 * 100 - pen}


def fit(corpus_path="evals/tasks/guardian_corpus.jsonl", weights_path=WEIGHTS_PATH, seed=7) -> dict:
    rows = load_jsonl(corpus_path)
    random.Random(seed).shuffle(rows)
    scam = [r for r in rows if r["label"] == "scam"]
    legit = [r for r in rows if r["label"] == "legit"]
    cut_s, cut_l = int(len(scam) * 0.7), int(len(legit) * 0.7)
    train = scam[:cut_s] + legit[:cut_l]
    test = scam[cut_s:] + legit[cut_l:]
    ftr = [_features(r) for r in train]
    fte = [_features(r) for r in test]
    cfg = json.loads(Path(weights_path).read_text(encoding="utf-8"))
    best = _metrics(cfg, train, ftr)["objective"]
    for _ in range(3):
        for k in list(cfg["weights"]):
            base = cfg["weights"][k]
            for m in (0.5, 0.75, 1.0, 1.25, 1.5):
                cfg["weights"][k] = round(base * m, 3)
                o = _metrics(cfg, train, ftr)["objective"]
                if o > best:
                    best, base = o, cfg["weights"][k]
            cfg["weights"][k] = base
        for b in [x / 2 for x in range(-12, -3)]:
            old = cfg["bias"]
            cfg["bias"] = b
            o = _metrics(cfg, train, ftr)["objective"]
            if o > best:
                best = o
            else:
                cfg["bias"] = old
        for t in (70.0, 75.0, 80.0, 85.0):
            old = cfg["threshold"]
            cfg["threshold"] = t
            o = _metrics(cfg, train, ftr)["objective"]
            if o > best:
                best = o
            else:
                cfg["threshold"] = old
    Path(weights_path).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    out = {"train": _metrics(cfg, train, ftr), "test": _metrics(cfg, test, fte),
           "n_train": len(train), "n_test": len(test), "threshold": cfg["threshold"], "bias": cfg["bias"]}
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    fit()
