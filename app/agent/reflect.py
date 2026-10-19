"""Grounding check: every number in the narrative must come from a tool output. Otherwise re-render from templates."""
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

from app.agent.types import Plan, ToolResult
from app.core.security import SecurityGuard

_UNIT = {"ty": 1e9, "trieu": 1e6, "tr": 1e6, "million": 1e6, "m": 1e6, "k": 1e3, "nghin": 1e3}
_UNIT_RE = r"(\d+(?:[.,]\d+)?)\s*(ty|trieu|tr|million|k|nghin)\b"


def extract_numbers(text: str) -> List[float]:
    t = SecurityGuard.normalize_text(text)
    out: List[float] = []
    for m in re.finditer(_UNIT_RE, t):
        out.append(float(m.group(1).replace(",", ".")) * _UNIT[m.group(2)])
    t2 = re.sub(_UNIT_RE, " ", t)
    for m in re.finditer(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", t2):
        out.append(float(m.group(0).replace(",", "")))
    return out


def collect_numbers(obj: Any, acc: Set[float] = None) -> Set[float]:
    acc = set() if acc is None else acc
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        for v in (float(obj), abs(float(obj))):
            acc.add(v)
            acc.add(round(v, 1))
            acc.add(float(round(v)))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, acc)
    elif isinstance(obj, str):
        for n in extract_numbers(obj):
            acc.add(n)
    return acc


@dataclass
class ReflectReport:
    grounded: bool
    unmatched: List[float] = field(default_factory=list)
    regenerated: bool = False


SAFE_SMALL = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 12.0, 20.0, 30.0, 50.0, 100.0, 365.0}   # counts, rule names, quiz sizes


class Reflector:
    @staticmethod
    def check(narrative: str, results: List[ToolResult], tolerance: float = 0.005, extra: Optional[List[Any]] = None) -> ReflectReport:
        pool: Set[float] = set()
        for r in results:
            collect_numbers(r.output, pool)
            collect_numbers(r.args, pool)
        for obj in extra or []:                      # queued / decided call arguments & preflight reasons are facts too
            collect_numbers(obj, pool)
        unmatched = []
        for n in extract_numbers(narrative):
            if n in SAFE_SMALL:
                continue
            if any(abs(n - p) <= tolerance * max(abs(p), 1.0) for p in pool):
                continue
            unmatched.append(n)
        return ReflectReport(grounded=not unmatched, unmatched=unmatched)

    @staticmethod
    def finalize(narrative: str, intent: str, plan: Plan, results: List[ToolResult], decisions, queued):
        extra = (
            [getattr(q, "args", {}) for q in queued]
            + [getattr(getattr(d, "call", None), "args", {}) for d in decisions]
            + [getattr(d, "reasons", []) for d in decisions]
        )
        rep = Reflector.check(narrative, results, extra=extra)
        if rep.grounded:
            return narrative, rep
        rep.regenerated = True
        return render_template(intent, plan, results, decisions, queued), rep


def _vnd(x: float) -> str:
    return f"{x:,.0f} VND"


def _out(results: List[ToolResult], tool: str) -> dict:
    return next((r.output for r in results if r.tool == tool and r.error is None), {})


def render_template(intent: str, plan: Plan, results: List[ToolResult], decisions, queued) -> str:
    lines: List[str] = []
    errors = [r for r in results if r.error]
    if intent == "budget_status":
        o = _out(results, "get_budget_status")
        so = _out(results, "scan_subscriptions")
        if o:
            b = o.get("breakdown", {})
            period = "Whole statement" if o.get("month") in (None, "all") else f"Month {o['month']}"
            cs = o.get("category_spend")
            if cs:
                cap = f" against your cap of {_vnd(cs['cap'])}" if cs.get("cap") else ""
                lines.append(f"{cs['category']} spending ({period.lower()}): {_vnd(cs['amount'])} in {cs['count']} transaction(s){cap}.")
                for x in cs.get("top", []):
                    lines.append(f"- {x['date']} {x['merchant']}: {_vnd(x['amount'])}")
            lines.append(f"{period}: Income {_vnd(o['total_income'])}, expenses {_vnd(o['total_expense'])}, "
                         f"net cash flow {_vnd(o.get('net_surplus', 0.0))}, savings rate {o['savings_rate_pct']}%.")
            for k in ("Needs", "Wants", "Savings"):
                if k in b:
                    lines.append(f"{k}: {_vnd(b[k]['amount'])} ({b[k]['actual_pct']}% vs target {b[k]['target_pct']}%), {b[k]['status']}.")
            if o.get("suggested_savings_sweep_vnd", 0) > 0:
                lines.append(f"Suggested sweep to Emergency Vault: {_vnd(o['suggested_savings_sweep_vnd'])}.")
            if o.get("later_transactions"):
                lines.append(f"{o['later_transactions']} later transaction(s) after {o['month']} are not included.")
        if so.get("subscriptions"):
            lines.append(f"Follow-up: {so['count']} recurring subscriptions cost {_vnd(so['total_annual_leakage'])} per year.")
    elif intent == "subscriptions":
        so = _out(results, "scan_subscriptions")
        subs = so.get("subscriptions", [])
        lines.append(f"Found {so.get('count', len(subs))} recurring subscriptions costing {_vnd(so.get('total_annual_leakage', 0.0))} per year.")
        for s in subs:
            lines.append(f"- {s['merchant']}: {_vnd(s['amount'])} every {s['frequency_days']} days ({s['status']}).")
    elif intent == "stress_test":
        o = _out(results, "run_stress_test")
        if o:
            i = o.get("inputs", {})
            if i.get("income_loss_months"):
                lines.append(f"Scenario: no income for the first {int(i['income_loss_months'])} month(s), then normal income.")
            lines.append(f"Resilience score {o['resilience_score']}/100; probability of running out of cash {o['bankruptcy_probability']}%; "
                         f"recommended buffer {_vnd(o['recommended_emergency_buffer'])}.")
            if i:
                lines.append(f"Inputs: income {_vnd(i['monthly_income'])}/month and spending {_vnd(i['monthly_expenses'])}/month "
                             f"from your statement, Emergency Vault {_vnd(i['initial_savings'])}.")
    elif intent == "second_opinion":
        o = _out(results, "second_opinion")
        if o:
            lines.append(f"Verdict on {o['item_name']} at {_vnd(o['price'])}: {o['verdict']} (confidence {o['confidence_score']}%).")
            for t in o.get("turns", []):
                lines.append(f"- {t['agent']}: {t['message']}")
    elif intent == "wallets":
        for w in _out(results, "get_wallets").get("wallets", []):
            lines.append(f"- {w['name']}: {_vnd(w['balance'])}")
    elif intent in ("transfer_internal", "transfer_external", "cancel_subscription"):
        g = _out(results, "guardian_scan")
        if g:
            if g.get("locked"):
                lines.append(f"Transfer frozen. Guardian risk {g['risk_score']}/100, pattern: {g.get('scam_type') or 'suspicious'}.")
                lines += [f"- {e}" for e in g.get("evidence", [])]
                lines.append("What you should know:")
                lines += [f"- {c}" for c in g.get("counter_facts", [])]
                lines.append("The request is in your approval queue. It unlocks after the cooling-off period and the safety quiz.")
            else:
                lines.append(f"Guardian risk {g['risk_score']}/100 ({g['level']}).")
                if g.get("level") == "HIGH":      # not frozen, but the user should see why before approving
                    lines.append("Before you approve, check:")
                    lines += [f"- {e}" for e in g.get("evidence", [])]
                    lines += [f"- {a}" for a in g.get("recommended_actions", [])]
                    lines += [f"- {c}" for c in g.get("counter_facts", [])[-1:]]   # the generic 'pause and verify' fact
        for r in results:
            if r.tool in ("transfer_internal", "transfer_external", "cancel_subscription") and r.error is None:
                lines.append(f"{r.tool}: {r.output.get('status', 'done')}. {r.output.get('message', '')}".strip())
                if r.tool == "cancel_subscription" and r.output.get("email_template_en"):
                    lines.append("Draft cancellation notice (not sent):")
                    lines.append(r.output["email_template_en"])
    elif intent == "scam_check":
        g = _out(results, "guardian_scan")
        read = bool(_out(results, "read_chat_screenshot").get("text"))
        if not read and not (g.get("locked") or g.get("level") == "HIGH"):
            lines.append("I could not read the screenshot (reading images needs the AI mode). "
                         "Paste the message as text and I will check it.")
        elif g:
            if g.get("locked") or g.get("level") == "HIGH":
                lines.append(f"Do not send money for this message. Guardian risk {g['risk_score']}/100, "
                             f"pattern: {g.get('scam_type') or 'suspicious'}.")
                lines += [f"- {e}" for e in g.get("evidence", []) if "never been paid" not in e]
                lines.append("What you should know:")
                lines += [f"- {c}" for c in g.get("counter_facts", [])]
            else:
                lines.append(f"Guardian risk {g['risk_score']}/100 ({g['level']}). Nothing in this message matches a known scam "
                             "pattern; still verify the sender through a channel you look up yourself before paying.")
            lines.append("Nothing was sent: I only read the screenshot.")
    elif intent == "set_budget":
        o = _out(results, "set_budget")
        if o:
            lines.append(o.get("message", "Budget updated."))
    elif intent == "explain_transaction":
        o = _out(results, "explain_transaction")
        if o:
            if not o.get("matches"):
                lines.append(f"No transaction matches '{o.get('query')}'.")
            else:
                first = o["matches"][0]
                lines.append(f"{o['occurrences']} transaction(s) match '{o.get('query')}', total {_vnd(o['total'])}; {o.get('label_reason', '')}.")
                lines.append(f"Latest: {first['date']} {first['description']} {_vnd(first['amount'])} ({first['category']} / {first['subcategory']}).")
                if o.get("recurring"):
                    lines.append(f"It recurs about every {o['average_gap_days']} days, so it is treated as a subscription.")
    elif intent == "read_receipt":
        d = _out(results, "read_receipt").get("data", {})
        if d:
            lines.append(f"Receipt from {d.get('merchant')} on {d.get('date')}: total {_vnd(float(d.get('total_amount', 0)))}, "
                         f"suggested category {d.get('suggested_category')}.")
    elif intent == "run_my_month":
        o = _out(results, "run_my_month_report")
        lines.append(o.get("summary", "Month review completed."))
        if o.get("advice"):
            lines.append("What to do about the suspected scam payment:")
            lines += [f"- {x}" for x in o["advice"]]
    elif intent == "scan_past_transactions":
        o = _out(results, "scan_past_transactions")
        if o:
            if not o.get("flagged"):
                lines.append(f"I checked {o['checked']} payments on your statement and none of them looks like a scam.")
            else:
                lines.append(f"I checked {o['checked']} payments: {len(o['flagged'])} look like a scam, "
                             f"{_vnd(o['flagged_total'])} in total.")
                for s in o["flagged"]:
                    lines.append(f"- {s['date']} {s['merchant']}: {_vnd(s['amount'])} (\"{s['description']}\", "
                                 f"risk {s['risk_score']}/100)")
                lines.append("What to do now:")
                lines += [f"- {x}" for x in o.get("advice", [])]
    elif intent == "recall":
        o = _out(results, "recall")
        facts = o.get("facts", {})
        if facts:
            lines.append("What I remember about you:")
            lines += [f"- {k.replace('_', ' ')}: {v}" for k, v in facts.items()]
        else:
            lines.append("I have not stored anything about you yet. Tell me with, for example, 'remember salary_day: 5'.")
        if o.get("budgets"):
            lines.append("Your monthly caps: " + ", ".join(f"{k} {_vnd(v)}" for k, v in o["budgets"].items()) + ".")
    elif intent == "clarify_cancel":
        lines.append("Which subscription should I cancel? Name it, for example 'cancel Netflix'. "
                     "Ask 'show my subscriptions' to see the list.")
    elif intent == "unknown":
        lines.append("I can help with budgets, subscriptions, stress tests, purchase second opinions, wallet transfers and scam checks. "
                     "Tell me what you need.")
    for q in queued:
        amt = q.args.get("amount")
        what = _vnd(float(amt)) if amt else ", ".join(f"{k}={v}" for k, v in q.args.items() if k not in ("evidence_text", "note", "human_approved"))
        lines.append(f"Queued for your approval: {q.tool} {what} ({q.verdict}).")
    for d in decisions:
        if getattr(d, "verdict", "") == "REJECT":
            reasons_joined = "; ".join(d.reasons)
            low_reasons = reasons_joined.lower()
            if d.call.tool == "transfer_external" and "ambiguous beneficiary" in low_reasons:
                who = d.call.args.get("payee_name") or "the recipient"
                bank = d.call.args.get("bank") or ""
                amt = float(d.call.args.get("amount") or 0)
                m_opts = re.search(r"\[(.+?)\]", reasons_joined)
                opts_list = [x.strip() for x in m_opts.group(1).split(";")] if m_opts else []
                bank_str = f" at {bank.title()}" if bank else ""
                lines.append(
                    f"Found {len(opts_list) or 'several'} saved contacts named '{who}'{bank_str} (the {_vnd(amt)} transfer has not been made):"
                )
                for idx_opt, opt in enumerate(opts_list, 1):
                    clean_opt = opt if re.match(r"^\d+\.", opt) else f"{idx_opt}. {opt}"
                    lines.append(f"  {clean_opt}")
                lines.append(
                    "Who should receive it? Please give the full name with the bank, or the account number."
                )
            elif d.call.tool == "transfer_external" and "missing beneficiary account number" in low_reasons:
                who = d.call.args.get("payee_name") or "the recipient"
                amt = float(d.call.args.get("amount") or 0)
                lines.append(
                    f"I cannot prepare the {_vnd(amt)} transfer to '{who}' without their account number. "
                    f"Please add the account number and bank, for example: 'send {_vnd(amt)} to {who} account 0123456789 Vietcombank'."
                )
            else:
                lines.append(f"Not executed: {d.call.tool}. {reasons_joined}.")
    for e in errors:
        lines.append(f"{e.tool} failed: {e.error}.")
    return "\n".join(lines) if lines else "Done."
