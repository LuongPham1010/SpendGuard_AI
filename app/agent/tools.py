"""Tool registry: every capability the agent can call, with JSON-schema params and tier rules."""
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.agent.types import AgentContext, PlannedCall
from app.config import TIER2_MAX_LIMIT_VND
from app.core.sandbox_wallets import wallet_manager
from app.core.audit_logger import SandboxAuditLogger
from app.core.security import SecurityGuard
from app.models.schemas import WalletTransferRequest, MonteCarloRequest, DebateRequest
from app.modules.auto_categorizer import AutoCategorizer
from app.modules.ghost_hunter import GhostSubscriptionHunter
from app.modules.monte_carlo import MonteCarloEngine
from app.modules.debate_arena import FinancialDebateArena
from app.modules.data_ingestion import DataIngestionEngine
import app.agent.memory as memory_mod
from app.modules.guardian import Guardian, TransferIntent, Evidence
import app.modules.guardian as guardian_mod

TierFn = Callable[[Dict[str, Any], AgentContext], str]
Handler = Callable[[Dict[str, Any], AgentContext], Dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    params: Dict[str, Any]
    tier: TierFn
    handler: Handler
    dry_run: Optional[Handler] = None


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def validate(self, call: PlannedCall) -> List[str]:
        if call.tool not in self._tools:
            return [f"unknown tool: {call.tool}"]
        errors: List[str] = []
        props = self._tools[call.tool].params.get("properties", {})
        for req in self._tools[call.tool].params.get("required", []):
            if req not in call.args:
                errors.append(f"missing arg: {req}")
        for k, v in call.args.items():
            if k not in props:
                errors.append(f"unexpected arg: {k}")
                continue
            t = props[k].get("type")
            if t == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
                errors.append(f"arg {k} must be a number")
            if t == "string" and not isinstance(v, str):
                errors.append(f"arg {k} must be a string")
        return errors

    def function_declarations(self) -> List[Dict[str, Any]]:
        return [{"name": s.name, "description": s.description, "parameters": s.params} for s in self._tools.values()]


def _tier1(_a, _c):
    return "Tier 1"


def _tier2(_a, _c):
    return "Tier 2"


def _tier3(_a, _c):
    return "Tier 3"


def _transfer_tier(args, _c):
    return "Tier 2" if float(args.get("amount", 0)) <= TIER2_MAX_LIMIT_VND else "Tier 3"


def _obj(props: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


def _not_wired(_a, _c):
    return {"status": "not_wired"}


_OCR_CACHE: Dict[str, dict] = {}     # image digest -> transcription, so Guardian does not read the same image twice


def _read_chat_screenshot(a, c):
    import hashlib
    from app.core.llm_gateway import gateway, Part
    img = c.images.get(a["attachment_id"])
    if not img:
        return {"available": False, "text": "", "reason": "attachment not found"}
    digest = hashlib.sha256(img).hexdigest()
    if digest in _OCR_CACHE:
        return dict(_OCR_CACHE[digest])
    res = gateway.generate("Transcribe every message in this chat screenshot verbatim as plain text.",
                           instructions="You are an OCR engine. Output only the transcribed text.",
                           untrusted=[Part(kind="image", content=img, mime_type="image/png", source="screenshot")],
                           purpose="chat_ocr")
    out = {"available": res.available, "text": res.text if res.available else "", "flags": res.flags}
    if res.available:
        if len(_OCR_CACHE) >= 64:
            _OCR_CACHE.clear()
        _OCR_CACHE[digest] = dict(out)
    return out


def _guardian_scan(a, c):
    intent = TransferIntent(amount=float(a["amount"]), payee_name=a.get("payee_name", ""),
                            payee_account=a.get("payee_account", ""), bank=a.get("bank", ""), note=a.get("note", ""))
    image_text = ""
    if a.get("evidence_image") and a["evidence_image"] in c.images:
        image_text = _read_chat_screenshot({"attachment_id": a["evidence_image"]}, c).get("text", "")
    return Guardian.assess(intent, Evidence(text=a.get("evidence_text", ""), image_text=image_text), c).model_dump()


def _transfer_external(a, c):
    if not a.get("human_approved"):
        return {"status": "REFUSED_NO_APPROVAL", "message": "External transfers execute only after human approval."}
    payee_account = str(a.get("payee_account") or "").strip()
    if not payee_account:
        payee_label = str(a.get("payee_name") or "the recipient").strip()
        return {
            "status": "REJECTED",
            "message": f"Missing beneficiary account number (STK) for {payee_label}. Please provide the recipient's account number and bank.",
        }
    amount = float(a["amount"])
    main = wallet_manager.get_wallet("main")
    vault = wallet_manager.get_wallet("emergency")
    from_main = min(amount, main.balance)
    from_vault = amount - from_main
    if from_vault > vault.balance:
        return {"status": "REJECTED", "message": "Insufficient sandbox funds."}
    main.balance -= from_main
    vault.balance -= from_vault
    if c.profile is not None and payee_account:
        memory_mod.profile_store.record_payee(c.profile, a.get("payee_name", ""), payee_account, str(a.get("bank") or ""))
    sig = json.dumps({"source": None, "destination": None, "payee_account": payee_account, "amount": amount}, sort_keys=True)
    SandboxAuditLogger.log_event(tier="Tier 3", module="SandboxWallets", action="EXTERNAL_TRANSFER",
                                 status="HUMAN_APPROVED_EXECUTED",
                                 details={"amount": amount, "payee": SecurityGuard.mask_pii(payee_account),
                                          "bank": a.get("bank", ""), "from_main": from_main, "from_vault": from_vault, "signature": sig})
    return {"status": "EXECUTED", "message": f"Sent {amount:,.0f} VND to {a.get('payee_name', 'payee')}.", "amount": amount,
            "from_main": from_main, "from_vault": from_vault,
            "new_main_balance": main.balance, "new_vault_balance": vault.balance}


def _month_report(a, c):
    caps = ", ".join(f"{k} {v:,.0f} VND" for k, v in (a.get("next_month_caps") or {}).items()) or "none needed"
    summary = (f"Month review complete. Savings rate {a.get('savings_rate_pct', 0)}%. "
               f"Swept {float(a.get('sweep_amount', 0)):,.0f} VND to the Emergency Vault. "
               f"Cancelled: {', '.join(a.get('cancelled') or []) or 'nothing'}. "
               f"Resilience score {a.get('resilience_score', 0)}/100. Next-month caps: {caps}.")
    scams = a.get("suspected_scams") or []
    if scams:
        listed = "; ".join(f"{float(s['amount']):,.0f} VND to {s['merchant']} on {s['date']}" for s in scams)
        summary = f"Warning: {len(scams)} payment(s) on your statement look like a scam: {listed}. " + summary
    return {"summary": summary, "advice": PAST_SCAM_ADVICE if scams else [],
            **{k: a.get(k) for k in ("sweep_amount", "cancelled", "resilience_score",
                                     "savings_rate_pct", "next_month_caps", "notes", "suspected_scams")}}


def _transfer_external_dry(a, c):
    amount = float(a.get("amount", 0))
    payee_account = str(a.get("payee_account") or "").strip()
    payee_name = str(a.get("payee_name") or "").strip()
    bank = str(a.get("bank") or "").strip()

    if not payee_account:
        from app.agent.planner import find_matching_payees
        matches = find_matching_payees(payee_name, bank, c)
        if len(matches) == 1:
            # Auto-fill if invoked directly with a unique saved payee
            a["payee_account"] = matches[0]["account"]
            a["payee_name"] = matches[0]["name"] or payee_name
            if not bank and matches[0].get("bank"):
                a["bank"] = matches[0]["bank"]
            payee_account = a["payee_account"]
        elif len(matches) > 1:
            options_str = "; ".join(
                f"{idx + 1}. {m['name']} ({m['bank'] or 'Bank'} - STK {m['account_masked']})"
                for idx, m in enumerate(matches)
            )
            bank_note = f" at {bank.title()}" if bank else ""
            return {
                "ok": False,
                "reason": (
                    f"ambiguous beneficiary '{payee_name}'{bank_note}: found {len(matches)} matching accounts in your saved contacts "
                    f"[{options_str}] — please specify the full name, bank, or account number (STK)"
                ),
            }
        else:
            who = f" for '{payee_name}'" if payee_name else ""
            return {
                "ok": False,
                "reason": f"missing beneficiary account number (STK){who} — please provide the recipient's bank account number and bank name",
            }

    main = wallet_manager.get_wallet("main")
    vault = wallet_manager.get_wallet("emergency")
    available = (main.balance if main else 0.0) + (vault.balance if vault else 0.0)
    if amount <= 0:
        return {"ok": False, "reason": "amount must be positive"}
    if amount > available:
        return {"ok": False, "reason": f"insufficient sandbox funds: {available:,.0f} VND available for {amount:,.0f} VND"}
    draw = max(0.0, amount - (main.balance if main else 0.0))
    return {"ok": True, "from_vault": draw, "note": f"will draw {draw:,.0f} VND from the Emergency Vault" if draw > 0 else ""}


def _check_payee(a, c):
    rep = guardian_mod.payee_reputation.lookup(a.get("account", ""), a.get("bank", ""))
    return {"account": memory_mod.mask_account(a.get("account", "")), "bank": a.get("bank", ""), **rep}


BUDGET_CATEGORIES = ("Dining", "Shopping", "Entertainment", "Groceries", "Transport", "Utilities", "Housing", "Healthcare", "Subscription")
# Spending questions may name a group of subcategories ("food" covers eating out and groceries)
SPEND_GROUPS = {"Food": ("Dining", "Groceries")}


def _is_income(t) -> bool:
    return t.type == "inflow" or t.category == "Income"


def _is_own_savings(t) -> bool:
    """Sweeps into the user's own vault move money between wallets; they are not spending."""
    return t.category == "Savings/Debts" and (t.subcategory == "Emergency Vault" or (t.merchant or "") == "Internal Transfer")


def stress_inputs(ctx: AgentContext) -> Dict[str, float]:
    """Monthly income and spending from the statement plus the vault balance: the one input set every stress test uses."""
    txs = ctx.transactions
    income_months = {str(t.date)[:7] for t in txs if _is_income(t)}
    n = max(1, len(income_months))
    income = sum(t.amount for t in txs if _is_income(t)) / n
    spending = sum(t.amount for t in txs if not _is_income(t) and not _is_own_savings(t)) / n
    if not income:
        income = float(getattr(ctx.profile, "monthly_income", 0.0) or 35_000_000.0) if ctx.profile is not None else 35_000_000.0
    vault = wallet_manager.get_wallet("emergency")
    return {"initial_savings": vault.balance if vault else 0.0, "monthly_income": round(income, 0),
            "monthly_expenses": round(spending, 0)}


def _run_stress_test(a, c):
    inputs = {**stress_inputs(c), **a}
    out = MonteCarloEngine.simulate(MonteCarloRequest(**inputs)).model_dump()
    out["inputs"] = inputs
    return out


def _budget_status(a, c):
    month = a.get("month") or AutoCategorizer.latest_statement_month(c.transactions)
    out = AutoCategorizer.analyze_spending_framework(c.transactions, month=None if month == "all" else month)
    if month and month != "all":
        out["later_transactions"] = sum(1 for t in c.transactions if str(t.date)[:7] > month)
    cat = str(a.get("category") or "").strip().title()
    if cat:
        subs = {s.lower() for s in SPEND_GROUPS.get(cat, (cat,))}
        rows = [t for t in c.transactions if not _is_income(t) and (t.subcategory or "").lower() in subs
                and (month in (None, "all") or str(t.date).startswith(month))]
        rows.sort(key=lambda t: t.amount, reverse=True)
        out["category_spend"] = {"category": cat, "amount": sum(t.amount for t in rows), "count": len(rows),
                                 "cap": (c.profile.budgets.get(cat) if c.profile is not None else None),
                                 "top": [{"date": t.date, "merchant": t.merchant or t.description, "amount": t.amount}
                                         for t in rows[:3]]}
    return out


PAST_SCAM_ADVICE = [
    "Call your bank's hotline now and ask them to trace or hold the transfer.",
    "Report it to the police and at canhbao.ncsc.gov.vn with the account number and screenshots.",
    "Do not pay any 'fee' to get the money back: recovery offers are a second scam.",
]


def scan_past_payments(ctx: AgentContext, log: bool = True) -> Dict[str, Any]:
    """Outflows already on the statement whose own description reads like a scam (proactive check)."""
    checked, flagged = 0, []
    for t in ctx.transactions:
        if _is_income(t) or _is_own_savings(t):
            continue
        checked += 1
        r = Guardian.content_risk(f"{t.description} {t.merchant or ''}")
        if r["suspicious"]:
            flagged.append({"id": t.id, "date": t.date, "amount": t.amount, "merchant": t.merchant or t.description,
                            "description": t.description, **r})
    flagged.sort(key=lambda x: x["date"], reverse=True)
    total = sum(x["amount"] for x in flagged)
    if log:
        SandboxAuditLogger.log_event(tier="Tier 1", module="GuardianHistory", action="SCAN_PAST_PAYMENTS",
                                     status="FLAGGED" if flagged else "CLEAN",
                                     details={"checked": checked, "flagged": len(flagged), "flagged_total": total,
                                              "ids": [x["id"] for x in flagged]})
    return {"checked": checked, "flagged": flagged, "flagged_total": total,
            "advice": PAST_SCAM_ADVICE if flagged else []}


def _find_subscription(merchant: str, ctx: AgentContext) -> Optional[dict]:
    q = SecurityGuard.normalize_text(merchant)
    if not q:
        return None
    for s in GhostSubscriptionHunter.detect_subscriptions(ctx.transactions):
        name = SecurityGuard.normalize_text(s.merchant)
        if name in q or (len(q) >= 3 and q in name):
            return s.model_dump()
    return None


def _cancel_subscription_dry(a, c):
    if _find_subscription(a.get("merchant", ""), c):
        return {"ok": True}
    return {"ok": False, "reason": f"no recurring subscription matching '{a.get('merchant', '')}' in your statement"}


def _cancel_subscription(a, c):
    sub = _find_subscription(a["merchant"], c)
    if not sub:
        return {"merchant": a["merchant"], "cancelled": False, "status": "NOT_FOUND",
                "message": f"No recurring subscription matching '{a['merchant']}' in your statement."}
    GhostSubscriptionHunter.cancel_subscription(sub["merchant"])
    return {"merchant": sub["merchant"], "cancelled": True, "status": "FLAGGED_FOR_CANCELLATION",
            "annual_saving": sub["annual_leakage"], "unsubscribe_url": sub["unsubscribe_url"],
            "email_template_en": sub["email_template_en"], "email_template_vi": sub["email_template_vi"],
            "message": f"{sub['merchant']} flagged for cancellation; saves {sub['annual_leakage']:,.0f} VND per year. "
                       f"Cancel at {sub['unsubscribe_url']} or send the drafted notice [simulated: nothing is sent]."}


def _set_budget(a, c):
    cat = str(a.get("category", "")).strip().title()
    cap = float(a.get("monthly_cap", 0))
    if cat not in BUDGET_CATEGORIES or cap <= 0:
        return {"status": "REJECTED", "message": f"category must be one of {', '.join(BUDGET_CATEGORIES)} and the cap positive"}
    previous = c.profile.budgets.get(cat)
    c.profile.budgets[cat] = cap
    memory_mod.profile_store.save(c.profile)
    SandboxAuditLogger.log_event(tier="Tier 2", module="Budget", action="SET_BUDGET_CAP", status="EXECUTED",
                                 details={"category": cat, "monthly_cap": cap, "previous": previous})
    return {"status": "SET", "category": cat, "monthly_cap": cap, "previous_cap": previous,
            "message": f"{cat} cap set to {cap:,.0f} VND per month."}


def _explain_transaction(a, c):
    q = SecurityGuard.normalize_text(str(a.get("query", "")))
    amount = None
    try:
        from app.agent.planner import extract_amount
        amount = extract_amount(q)
    except Exception:
        amount = None
    matches = []
    for t in c.transactions:
        hay = SecurityGuard.normalize_text(f"{t.description} {t.merchant or ''} {t.id}")
        if (q and q in hay) or (t.merchant and SecurityGuard.normalize_text(t.merchant) in q) or (amount and abs(t.amount - amount) < 1):
            matches.append(t)
    matches.sort(key=lambda t: t.date)
    out = [{"id": t.id, "date": t.date, "description": t.description, "amount": t.amount, "type": t.type,
            "category": t.category, "subcategory": t.subcategory, "merchant": t.merchant} for t in matches[:10]]
    recurring = False
    gap_days = None
    if len(matches) >= 2:
        from datetime import datetime
        try:
            d = [datetime.strptime(t.date, "%Y-%m-%d") for t in matches]
            gaps = [(d[i] - d[i - 1]).days for i in range(1, len(d))]
            gap_days = round(sum(gaps) / len(gaps), 1)
            recurring = all(25 <= g <= 35 for g in gaps)
        except Exception:
            pass
    reason = ""
    if out:
        cat, sub = AutoCategorizer.classify_transaction(matches[0].description, matches[0].category)
        reason = f"labelled {cat} / {sub} by the keyword rules"
    return {"query": a.get("query", ""), "matches": out, "occurrences": len(matches), "recurring": recurring,
            "average_gap_days": gap_days, "total": sum(t.amount for t in matches), "label_reason": reason}


def _remember(a, c):
    c.profile.facts[a["key"]] = a["value"]
    memory_mod.profile_store.save(c.profile)
    return {"stored": {a["key"]: a["value"]}}


def _recall(a, c):
    if a.get("key"):
        return {"facts": {a["key"]: c.profile.facts.get(a["key"])}}
    return {"facts": dict(c.profile.facts), "monthly_income": c.profile.monthly_income, "budgets": c.profile.budgets}


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()

    reg.register(ToolSpec("get_transactions", "List ingested statement transactions.",
        _obj({"limit": {"type": "number"}}), _tier1,
        lambda a, c: {"count": len(c.transactions),
                      "transactions": [t.model_dump() for t in c.transactions[-int(a.get("limit", 50)):]]}))

    reg.register(ToolSpec("get_budget_status",
        "50/30/20 breakdown, income, expenses, savings gap for one month (default: latest month with income; 'all' = whole "
        "statement), optionally the spending in one category (Dining, Groceries, Food, Shopping, Transport, ...).",
        _obj({"month": {"type": "string"}, "category": {"type": "string"}}), _tier1, _budget_status))

    def _categorize(a, c):
        counts = {}
        for t in c.transactions:
            cat, sub = AutoCategorizer.classify_transaction(t.description, t.category)
            t.category, t.subcategory = cat, sub
            counts[cat] = counts.get(cat, 0) + 1
        return {"categorized": len(c.transactions), "by_category": counts}

    reg.register(ToolSpec("categorize_transactions", "Re-run 50/30/20 categorisation over the ingested statement.",
        _obj({}), _tier1, _categorize))

    reg.register(ToolSpec("scan_subscriptions", "Detect recurring subscriptions and annual leakage.",
        _obj({}), _tier1,
        lambda a, c: (lambda subs: {"subscriptions": subs, "count": len(subs),
                                     "total_annual_leakage": sum(x["annual_leakage"] for x in subs),
                                     "active_annual_leakage": sum(x["annual_leakage"] for x in subs if x["status"] == "active")})(
            [s.model_dump() for s in GhostSubscriptionHunter.detect_subscriptions(c.transactions)])))

    reg.register(ToolSpec("cancel_subscription", "Flag a subscription for cancellation and generate the notice.",
        _obj({"merchant": {"type": "string"}, "human_approved": {"type": "boolean"}}, ["merchant"]), _tier2,
        _cancel_subscription, _cancel_subscription_dry))

    reg.register(ToolSpec("run_stress_test",
        "Monte Carlo 12-month cash-flow stress test on the statement's monthly income and spending and the vault balance; "
        "income_loss_months simulates a job loss.",
        _obj({"initial_savings": {"type": "number"}, "monthly_income": {"type": "number"},
              "monthly_expenses": {"type": "number"}, "income_loss_months": {"type": "number"}}), _tier1,
        _run_stress_test))

    reg.register(ToolSpec("get_wallets", "Current sandbox wallet balances.", _obj({}), _tier1,
        lambda a, c: {"wallets": [w.model_dump() for w in wallet_manager.get_all_wallets()]}))

    def _transfer_internal(a, c):
        req = WalletTransferRequest(source_wallet=a["source"], destination_wallet=a["destination"],
                                    amount=float(a["amount"]), note=a.get("note", ""),
                                    security_override=bool(a.get("human_approved", False)))
        return wallet_manager.execute_transfer(req).model_dump()

    def _transfer_internal_dry(a, c):
        src = wallet_manager.get_wallet(a.get("source", ""))
        dst = wallet_manager.get_wallet(a.get("destination", ""))
        ok = bool(src and dst and src.id != dst.id and src.balance >= float(a.get("amount", 0)) > 0)
        return {"ok": ok, "source_balance": src.balance if src else None}

    reg.register(ToolSpec("transfer_internal", "Move money between the user's own sandbox wallets.",
        _obj({"source": {"type": "string"}, "destination": {"type": "string"}, "amount": {"type": "number"},
              "note": {"type": "string"}, "evidence_text": {"type": "string"}, "human_approved": {"type": "boolean"}},
             ["source", "destination", "amount"]),
        _transfer_tier, _transfer_internal, _transfer_internal_dry))

    reg.register(ToolSpec("transfer_external", "Send money to an outside payee (always high-risk).",
        _obj({"payee_name": {"type": "string"}, "payee_account": {"type": "string"}, "bank": {"type": "string"},
              "amount": {"type": "number"}, "note": {"type": "string"}, "source": {"type": "string"},
              "evidence_text": {"type": "string"}, "evidence_image": {"type": "string"},
              "human_approved": {"type": "boolean"}},
             ["payee_name", "payee_account", "amount"]),
        _tier3, _transfer_external, _transfer_external_dry))

    reg.register(ToolSpec("guardian_scan", "Score a transfer for scam risk using rules, behavior and evidence.",
        _obj({"payee_name": {"type": "string"}, "payee_account": {"type": "string"}, "bank": {"type": "string"},
              "amount": {"type": "number"}, "note": {"type": "string"},
              "evidence_text": {"type": "string"}, "evidence_image": {"type": "string"}}, ["amount"]),
        _tier1, _guardian_scan))

    reg.register(ToolSpec("second_opinion", "Three-agent debate on a purchase decision.",
        _obj({"item": {"type": "string"}, "price": {"type": "number"}, "justification": {"type": "string"},
              "income": {"type": "number"}}, ["item", "price"]), _tier1,
        lambda a, c: FinancialDebateArena.run_debate(DebateRequest(
            item_name=a["item"], price=float(a["price"]), user_justification=a.get("justification", ""),
            user_income=float(a.get("income", 35_000_000.0)))).model_dump()))

    reg.register(ToolSpec("read_receipt", "OCR a receipt image attachment.",
        _obj({"attachment_id": {"type": "string"}}, ["attachment_id"]), _tier1,
        lambda a, c: DataIngestionEngine.extract_receipt_ocr(c.images.get(a["attachment_id"], b""),
                                                             filename=a["attachment_id"])))

    reg.register(ToolSpec("read_chat_screenshot", "Extract text from a chat screenshot attachment.",
        _obj({"attachment_id": {"type": "string"}}, ["attachment_id"]), _tier1, _read_chat_screenshot))

    reg.register(ToolSpec("run_my_month_report", "Compose the month review report from computed values.",
        _obj({"sweep_amount": {"type": "number"}, "cancelled": {"type": "array", "items": {"type": "string"}},
              "resilience_score": {"type": "number"}, "savings_rate_pct": {"type": "number"},
              "next_month_caps": {"type": "object"}, "notes": {"type": "array", "items": {"type": "string"}},
              "suspected_scams": {"type": "array", "items": {"type": "object"}}}),
        _tier1, _month_report))

    reg.register(ToolSpec("scan_past_transactions",
        "Check payments already on the statement for scam patterns (task scams, Ponzi yields, fake officials) and say what to do.",
        _obj({}), _tier1, lambda a, c: scan_past_payments(c)))

    reg.register(ToolSpec("check_payee", "Look up a payee account on the scam warning list.",
        _obj({"account": {"type": "string"}, "bank": {"type": "string"}}, ["account"]), _tier1, _check_payee))

    reg.register(ToolSpec("set_budget", "Set a monthly spending cap for a category (Dining, Shopping, ...).",
        _obj({"category": {"type": "string"}, "monthly_cap": {"type": "number"}, "human_approved": {"type": "boolean"}},
             ["category", "monthly_cap"]), _tier2, _set_budget))

    reg.register(ToolSpec("explain_transaction", "Find transactions matching a merchant, id or amount and explain their label and recurrence.",
        _obj({"query": {"type": "string"}}, ["query"]), _tier1, _explain_transaction))

    reg.register(ToolSpec("remember", "Store a durable fact about the user.",
        _obj({"key": {"type": "string"}, "value": {"type": "string"}}, ["key", "value"]), _tier1, _remember))

    reg.register(ToolSpec("recall", "Retrieve stored facts about the user.",
        _obj({"key": {"type": "string"}}), _tier1, _recall))

    return reg

