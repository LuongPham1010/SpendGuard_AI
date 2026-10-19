"""Generate the unseen Guardian suite with a live model and write evals/tasks/guardian_unseen.jsonl.

The resulting rows are never used to write rules or fit weights. The prompt below is the exact prompt used for the
committed file (generated 2026-10-13 with gemini-3.8-flash). Re-running produces a different sample; keep the committed
file for comparability and add a new file (for example guardian_unseen_v2.jsonl) when regenerating.

Usage: python -m evals.generate_unseen [--out evals/tasks/guardian_unseen.jsonl] [--n 30]
Requires GEMINI_API_KEY. The model also proposes `payee_new`; review that column by hand before relying on it.
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROMPT = (
    "Write {n} short messages a Vietnamese bank customer might receive or type when about to transfer money. "
    "{half} must be scams (mix: fake police/prosecutor, fake bank security, task/commission jobs, investment with promised returns, "
    "OTP requests, prize fees, romance, customs fees, fake relative in trouble, fake refund, fake transfer receipt). "
    "{half} must be legitimate everyday payments (rent, tuition, family, friends, shops, utilities, deposits that were verified in person), "
    "and at least 6 of the legitimate ones must contain words like urgent, today, deadline, refund, hospital or fine. "
    "Vary wording; do NOT reuse stock phrases such as 'tai khoan tam giu' or 'chuyen gap'. Half Vietnamese with diacritics, half English. "
    "Return JSON: {{\"cases\": [{{\"text\": str, \"label\": \"scam\"|\"legit\", \"amount_vnd\": number, \"payee_new\": bool}}]}}"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evals/tasks/guardian_unseen.jsonl")
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    from app.core.llm_gateway import gateway
    if not gateway.available:
        print("A live model is required (set GEMINI_API_KEY).", file=sys.stderr)
        return 1
    prompt = PROMPT.format(n=args.n, half=args.n // 2)
    res = gateway.generate(prompt, instructions="You write realistic test data. Output only JSON.", schema={"type": "object"}, purpose="unseen_gen")
    cases = (res.data or {}).get("cases", [])
    if len(cases) < args.n * 2 // 3:
        print("generation failed:", res.flags, (res.text or "")[:200], file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for i, c in enumerate(cases, 1):
            f.write(json.dumps({"id": f"u{i:03d}", "text": c["text"], "amount": float(c.get("amount_vnd", 5_000_000)),
                                "payee_new": bool(c.get("payee_new", True)), "label": c["label"],
                                "source_note": f"written by {res.model} via evals/generate_unseen.py; never used for rule writing or fitting"},
                               ensure_ascii=False) + "\n")
    print(f"wrote {len(cases)} rows to {out} (model {res.model})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
