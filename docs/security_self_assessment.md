# SpendGuard AI — Security Self-Assessment Report

Scope: the SpendGuard agent as submitted (branch `agent-core`). All actions operate on sandbox wallets; no real financial rails are connected.

## Three-layer flow

```
User request + attachments + statement rows
   ▼
Layer 1 — Input guardrails            app/core/security.py (scan_injection, mask_pii), app/agent/orchestrator.py GUARDRAIL
   • injection patterns scanned on the request and on every ingested CSV description
   • PII masked before anything reaches a model: app/core/llm_gateway.py wraps untrusted content in <untrusted_data> blocks
   ▼
LLM planner / rule planner             app/agent/planner.py (LLM output validated against the registry; rules always available)
   ▼
Layer 2 — Security validator           app/agent/preflight.py
   • argument validation, tier classification, dry-run (balance, wallet existence)
   • Guardian assessment for outbound transfers and vault drains (app/modules/guardian.py)
   • duplicate detection (10 minutes), Tier 2 daily cap, injection downgrade
   ▼
Tier matrix                            app/core/security.py evaluate_tier + per-tool tier functions in app/agent/tools.py
   Tier 1 / Tier 2 → execute + notify   Tier 3 / LOCKED → approval queue + one-time code (app/agent/approvals.py)
   ▼
Layer 3 — Output audit                 app/core/audit_logger.py (SHA-256 chained, accounts masked), app/agent/reflect.py (number grounding)
```

## Permission-tier implementation

| Tier | Actions | Policy | Implementation |
|---|---|---|---|
| Tier 1 — read-only and synthesis | budget status, transactions, subscription scan, stress test, second opinion, wallet balances, Guardian scan, receipt and screenshot OCR, memory | executes autonomously, no confirmation | `_tier1` in `app/agent/tools.py`; `SecurityGuard.evaluate_tier` READ_ONLY branch |
| Tier 2 — controlled execution | internal transfers ≤ 5,000,000 VND, subscription cancellation flags, savings sweeps, budget-cap changes | executes autonomously, audit entry and user notification (simulated push), daily cap 10,000,000 VND across money tools | `_transfer_tier`, `TIER2_MAX_LIMIT_VND`, `TIER2_DAILY_CAP_VND`, `Preflight._tier2_spent_today` |
| Tier 3 — high-risk | internal transfers > 5,000,000 VND, every external transfer, vault drains > 50 %, any action after an injection flag | paused; summarised in the approval queue; executes only after an explicit human decision confirmed with a one-time code (simulated SMS, hash stored, 5-minute expiry, 3 attempts); re-validated at decision time | `Preflight.check` → `AWAIT_HUMAN`; `ApprovalQueue.decide` re-runs preflight and passes `human_approved=True` |
| LOCKED (Guardian) | transfers with scam risk ≥ 70 (fitted threshold) and a content cue | frozen; cooling-off (60 s demo, 3,600 s production); quiz with three questions; one-time code; trusted-contact notice (simulated) | `Guardian.assess`, `ApprovalQueue._quiz_ok`, `unlock.cooling_off_until` |

External transfers refuse to execute without `human_approved` even if called directly (`_transfer_external` in `app/agent/tools.py`).

## PII handling

`SecurityGuard.mask_pii` masks card numbers, national IDs, prefixed bank accounts, phone numbers and e-mail addresses in free text; payee fields in audit entries and tool outputs are masked with `mask_account` (3 + 3 digits kept) regardless of format. The gateway applies `mask_pii` to every text part before a prompt is built. Statement descriptions are masked at ingestion. The audit logger masks every 9–16 digit run in entry details before writing (3 + 3 digits kept) and stores transfer signatures only as a SHA-256 digest, so neither the log file nor the in-memory ledger holds a full account number.

## Prompt-injection defence

Untrusted content (statement rows, receipts, screenshots, pasted messages, the user's own request) is wrapped in `<untrusted_data source="…">` blocks under a system preamble that declares it data, never instructions. The injection scanner flags matches; a flagged turn forces every non-read-only action to the approval queue. Injection regression suite: 12/12 listed-pattern payloads flagged and downgraded. Novel phrasings (6, Vietnamese and paraphrased): 1/6 flagged; the injected text changed executed actions in 0/6 cases, because planning reads only the user's request and money is tier-gated. The pattern list is a regression check, not a detector.

## Operational safeguards

| Control | Implementation |
|---|---|
| Iteration cap | `MAX_ITERATIONS = 5` plan/replan rounds per turn (the agent uses 2); at most `PLANNER_MAX_CALLS = 6` calls per plan, replan adds at most 2 read-only calls |
| Circuit breaker | two consecutive tool errors stop the turn: remaining calls are rejected with the reason, replan is skipped, `CIRCUIT_OPEN` is logged (`app/agent/orchestrator.py`) |
| Duplicate guard | the same transfer within 10 minutes is rejected (`Preflight._is_duplicate`, signature digests) |
| Proactive scan | payments already on the statement are checked for scam content; the month review opens with a warning and recovery advice (`scan_past_transactions`) |

## Hallucination control

Every number the agent states is checked against tool outputs by the Reflector; unmatched numbers cause the deterministic template to replace the narrative. The Guardian keeps model-provided evidence quotes only if they are exact substrings of the input. The debate's facts (price, income share, opportunity cost, balances, runway) are computed in Python and if any persona fails to cite them the whole debate falls back to the deterministic engine.

## Human-in-the-loop

Approval queue with approve/reject, cooling-off, quiz gating for locked requests, stale-state re-check, and an approval history in the user profile. Approving does not bypass preflight.

## Audit

Every state change and every model call is appended to `logs/sandbox_execution.log` with a SHA-256 hash chained to the previous entry (`SandboxAuditLogger`). Verification: recompute `sha256(prev_hash | timestamp | tier | module | action | status | details)` line by line and compare the first 16 hex characters.

## Model-assisted detection

**With the model enabled** (`SPENDGUARD_EVAL_LLM=1`, Gemini, report in `evals/results_llm/`): functional 22/22; regression corpus lock F1 0.99 (text-only 0.97); unseen lock F1 0.97 (precision 0.94, recall 1.00, text-only 0.93, velocity worst case 0.97); injection regression 12/12; novel phrasings flagged 0/6, executed actions changed in 0/6 (live run of 13 October, before the semantic injection patterns were added; the offline run now flags 1/6). The model's judgment counts as a content cue only when it is at least 0.90 confident and quotes the exact words it reacted to; the live functional check verifies intent, tools and verdicts on the live run and the wording on the deterministic rendering of the same results.

## Known-risk list

| Risk | Impact | Mitigation | Residual |
|---|---|---|---|
| Data leaves the device when a Gemini key is configured | masked financial text and images are sent to a third-party model | masking at the gateway; `LLM_PROVIDER=none` disables all model calls; the whole product works offline | residual exposure of masked content; data-residency depends on the provider |
| Regex PII masking is best-effort | unusual formats may pass unmasked | conservative patterns for VN IDs, cards, accounts, phones, e-mails | unmasked edge cases possible |
| Injection detection is a pattern blocklist | novel phrasings are not flagged | data/instruction separation at the gateway; tier gating means a missed injection still cannot move money above Tier 2 without a human | undetected low-tier manipulation of narrative text |
| Guardian corpus is team-written and the rules were written from it | the corpus F1 (0.99) is rule coverage, not performance | an unseen, model-written set is reported separately (lock F1 0.77, text-only F1 0.64, escalation with cue 0.67) and is never used for rule writing or fitting; weights refit when real reports are added | F1 on real traffic unknown; expect the unseen numbers, not the corpus number |
| Guardian false positives on urgent payments to new payees | legitimate users hit the quiz | lock requires a content cue; behavioural-only cases go to approval instead | about one in fifteen legitimate payments in the unseen set; details per row in the report |
| Single-user in-memory state | restarts reset wallets and approvals | profile persisted to JSON; audit log on disk | no multi-user isolation |
| Demo cooling-off is 60 seconds | shorter than a production cooling-off | `DEMO_COOLING_OFF_SECONDS`; production value 3,600 documented | demo only |
| No real bank or notification integration | trusted-contact notice and cancellations are simulated | explicit "[simulated]" labels in responses and logs | none in sandbox |
| Keyword categoriser | misclassified merchants skew the 50/30/20 view | model classification for unknown descriptions when available; user can relabel | offline accuracy limited to the keyword list |
| Payee blocklist is team-curated and shipped with demo placeholders | a real reported account is only caught if someone added it | lookup sources documented (tinnhiemmang.vn, canhbao.ncsc.gov.vn, police bulletins); HTTP provider hook via `PAYEE_LOOKUP_URL` | no live feed; coverage depends on curation |
| Subscription usage unknown | cancellations cannot be inferred from statements | only merchants the user marked unused are cancelled automatically | none |
| Approval queue is process-global and unauthenticated | any client of the single-user server can decide any request | single-user non-goal; `session_id` is recorded on every request; every approval needs a one-time code | no multi-user isolation |
| Safety quiz is three fixed questions | a coached victim can be told the answers; the sensible option is easy to guess | answers are checked on the server and never sent to the browser; the quiz is one gate among cooling-off, one-time code and trusted-contact notice | quiz alone is weak friction; rotating, scenario-specific questions are future work |
| Model mode is slow and quota-bound | with Gemini enabled a turn takes about 15–35 s (3–5 model calls); an exhausted key adds a retry | the console shows progress while it works; keys rotate and the last working key is tried first; categorisation and screenshot reading are cached; with no key left every path falls back to rules | latency depends on the provider; screenshots cannot be read when all keys are exhausted |
| One-time code and notifications are simulated | the code is shown on screen instead of being sent by SMS; notifications live in memory | labelled "[simulated SMS]" / "simulated push"; only the code's hash is stored | needs an SMS / push provider in production |

## Evidence

- `logs/sandbox_execution.log` — chained execution log (sandbox operation evidence; gitignored, produced by running the app, the tests or the evaluation).
- `evals/results/report.json`, `evals/results/report.md` — evaluation report (functional, Guardian, adversarial).
- `evidence/` — scripted end-to-end run: chained log with masked accounts and a readable transcript; `python scripts/generate_evidence.py`, verify with `python scripts/verify_audit_chain.py`.
- `tests/` — 201 automated tests; `python -m pytest -q`.
- Demo video — see `docs/demo_script.md` for the recorded scenarios.
