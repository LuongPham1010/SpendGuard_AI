# Execution evidence (deliverable 06)

| File | What it is |
|---|---|
| `sandbox_execution_evidence.log` | Chained SHA-256 audit log of one scripted end-to-end run in the sandbox. Account and card numbers are masked before anything is written. |
| `transcript.md` | The same run in readable form: every request, the tools the agent chose, each tool's tier and verdict, and the agent's answer. |

## What the run covers
1. Reading the 50-transaction statement, analysing the budget, and moving money into the Emergency Vault on the agent's own authority (Tier 2). Topic A's execution-evidence chain.
2. Flagging a scam payment that is already on the statement (proactive check).
3. A Tier 3 top-up waiting for the human. It is refused with no code and with a wrong code, then executed with the simulated OTP.
4. A fake-police transfer that Guardian freezes. Unlocking is refused during cooling-off and with wrong quiz answers, then the user cancels.
5. A legitimate payment to a new payee. It is escalated for approval, not frozen.
6. A prompt injection hidden in a statement row. Autonomy is downgraded for the turn and the action waits for the human.
7. A duplicate transfer blocked within 10 minutes.

## Reproduce and verify
```
python scripts/generate_evidence.py
python scripts/verify_audit_chain.py evidence/sandbox_execution_evidence.log
```
The run is offline (no model calls). It uses a temporary profile and temporary wallets, so `data/memory` is not touched. Cooling-off is shortened to 2 seconds so the script finishes; the production value is 3,600 seconds.
