# SpendGuard evaluation report

LLM backend available: False

## Functional: 22/22 (100%)

## Guardian regression corpus (team-written; rules were written from it): precision 0.987, recall 1.0, F1 0.993

Confusion: {'tp': 75, 'fp': 1, 'fn': 0, 'tn': 67} | text-only (payee treated as known): F1 0.739 {'tp': 44, 'fp': 0, 'fn': 31, 'tn': 68} | velocity worst case: F1 0.993 {'tp': 75, 'fp': 1, 'fn': 0, 'tn': 67}

Recall by labelled scam type (regression corpus): authority_impersonation 1.0, investment_ponzi 1.0, otp_request 1.0, prize 1.0, romance 1.0, customs_fee 1.0, safe_account 1.0, refund_scam 1.0, relative_emergency 1.0, fake_receipt 1.0, reported_account 1.0

## Novel injection phrasings (not in the blocklist, 6): flagged 1/6; the injected text changed what the agent executed in 0/6 cases

## Guardian on unseen model-written cases (30): lock precision 0.909, lock recall 0.667, lock F1 0.769, escalation-with-cue recall 0.667

Confusion (lock): {'tp': 10, 'fp': 1, 'fn': 5, 'tn': 14} | text-only: F1 0.636 {'tp': 7, 'fp': 0, 'fn': 8, 'tn': 15} | velocity worst case: F1 0.769 {'tp': 10, 'fp': 1, 'fn': 5, 'tn': 14}

## Adversarial: 12/12 blocked
