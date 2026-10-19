"""Deterministic intent planner (always available) with safe multi-turn merchant resolution and payee disambiguation."""
import re
from typing import Any, Dict, List, Optional

from app.agent.tools import ToolRegistry
from app.agent.types import AgentContext, Plan, PlannedCall
from app.core.security import SecurityGuard
from app.core.llm_gateway import gateway, Part
import app.agent.memory as memory_mod

_UNIT = {"ty": 1_000_000_000, "trieu": 1_000_000, "tr": 1_000_000, "m": 1_000_000, "million": 1_000_000,
         "k": 1_000, "nghin": 1_000, "ngan": 1_000}

_ACCOUNT_PREFIXED = r"(?:stk|so tai khoan|account|acct|tk)[:\s]*(\d{6,16})"


def extract_amount(text: str) -> Optional[float]:
    t = SecurityGuard.normalize_text(text)
    t = re.sub(_ACCOUNT_PREFIXED, " ", t)          # an account number is never the amount
    m = re.search(r"(\d+)\s*(tr|trieu)\s*(\d)\b", t)          # "2tr5" = 2.5 million
    if m:
        return float(m.group(1)) * 1_000_000 + float(m.group(3)) * 100_000
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(ty|trieu|tr|million|m|k|nghin|ngan)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * _UNIT[m.group(2)]
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,})", t)
    if m:
        return float(re.sub(r"[.,]", "", m.group(1)))
    return None


_BANKS = ["vietcombank", "techcombank", "mb bank", "mbbank", "bidv", "vietinbank", "acb", "tpbank", "vpbank",
          "sacombank", "agribank", "ocb", "hdbank", "msb", "seabank", "vib", "shb", "webank"]


def _canon_bank(bank_str: str) -> str:
    b = SecurityGuard.normalize_text(str(bank_str or "")).replace(" ", "")
    if b in ("mb", "mbbank"):
        return "mbbank"
    if b in ("vcb", "vietcombank"):
        return "vietcombank"
    if b in ("tcb", "techcombank"):
        return "techcombank"
    return b


def _strip_bank_from_name(raw_name: str) -> str:
    cleaned = raw_name.strip()
    for b in sorted(_BANKS, key=len, reverse=True):
        cleaned = re.sub(rf"\s+(?:ngan hang\s+|bank\s+|tai\s+|at\s+|ben\s+)?\b{re.escape(b)}\b.*$", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s+\b(ngan hang|bank|tai|at)\b\s*$", "", cleaned, flags=re.I).strip()
    return cleaned


def _payee_field(info: Any, key: str, default: str = "") -> str:
    if isinstance(info, dict):
        return str(info.get(key, default) or default)
    return str(getattr(info, key, default) or default)


def find_matching_payees(name: str, bank: str, ctx: Optional[AgentContext]) -> List[Dict[str, str]]:
    """Return all saved payees in ctx.profile.known_payees matching `name` (and `bank` if specified)."""
    if not name or ctx is None or getattr(ctx, "profile", None) is None:
        return []
    known = getattr(ctx.profile, "known_payees", None) or {}
    norm_query = SecurityGuard.normalize_text(_strip_bank_from_name(name))
    if not norm_query:
        return []
    query_tokens = [tok for tok in re.split(r"\W+", norm_query) if tok]
    if not query_tokens:
        return []

    target_bank = _canon_bank(bank)
    exact_matches: List[Dict[str, str]] = []
    partial_matches: List[Dict[str, str]] = []

    for saved_acc, info in known.items():
        acc_str = str(saved_acc).strip()
        if not re.fullmatch(r"\d{6,16}", acc_str):
            continue
        raw_saved_name = _payee_field(info, "name", "")
        saved_bank = _payee_field(info, "bank", "")
        masked = _payee_field(info, "account_masked", "") or memory_mod.mask_account(acc_str)

        norm_saved = SecurityGuard.normalize_text(raw_saved_name)
        if not norm_saved:
            continue
        saved_tokens = [tok for tok in re.split(r"\W+", norm_saved) if tok]

        # Bank filter: if user explicitly specified a bank, only consider payees matching that bank
        if target_bank:
            if not saved_bank or _canon_bank(saved_bank) != target_bank:
                continue

        entry = {
            "account": acc_str,
            "name": raw_saved_name,
            "bank": saved_bank,
            "account_masked": masked,
        }

        if norm_saved == norm_query:
            exact_matches.append(entry)
        elif all(qt in saved_tokens for qt in query_tokens):
            partial_matches.append(entry)

    # If the user typed a full name that matches one or more records exactly, prefer exact matches over partial ones
    return exact_matches if exact_matches else partial_matches


def extract_payee(text: str, ctx: Optional[AgentContext] = None) -> Dict[str, str]:
    t = SecurityGuard.normalize_text(text)
    account = ""
    m = re.search(_ACCOUNT_PREFIXED, t)
    if m:
        account = m.group(1)
    else:
        amount = extract_amount(text)
        amount_digits = str(int(amount)) if amount else ""
        for cand in re.findall(r"\b(\d{9,16})\b", t):
            if cand != amount_digits:              # bare digit runs are accounts only when they are not the amount
                account = cand
                break
    bank = next((b for b in _BANKS if b in t), "")
    name = ""
    m = re.search(r"(?:cho|to|den|for)\s+([a-z0-9][a-z0-9 ]{1,40}?)(?=,|\s+(?:stk|so tai khoan|account|acct|tk|at|tai)\b|\s+\d|$)", t)
    if m:
        name = _strip_bank_from_name(m.group(1).strip())

    # Resolve against known_payees ONLY when there is a single unambiguous match
    if not account and name and ctx is not None and getattr(ctx, "profile", None) is not None:
        matches = find_matching_payees(name, bank, ctx)
        if len(matches) == 1:
            account = matches[0]["account"]
            name = matches[0]["name"] or name
            if not bank and matches[0].get("bank"):
                bank = matches[0]["bank"]

    return {"payee_name": name, "payee_account": account, "bank": bank}


_CATEGORY_WORDS = [
    ("Dining", r"dining|eating out|an uong|an ngoai|coffee|cafe"),
    ("Shopping", r"shopping|mua sam|quan ao|clothes"),
    ("Entertainment", r"entertainment|giai tri|xem phim|game"),
    ("Groceries", r"grocer|thuc pham|di cho|sieu thi"),
    ("Transport", r"transport|di lai|xang|grab|taxi"),
    ("Utilities", r"utilit|dien nuoc|internet|tien dien"),
    ("Housing", r"housing|rent|tien nha|thue nha"),
    ("Healthcare", r"health|y te|thuoc|benh vien"),
    ("Subscription", r"subscription|thue bao"),
]


def _budget_category(normalized_text: str) -> Optional[str]:
    for cat, pat in _CATEGORY_WORDS:
        if re.search(pat, normalized_text):
            return cat
    return None


def _spend_category(normalized_text: str) -> Optional[str]:
    """Category named in a spending question; 'food' / 'tien an' covers eating out and groceries together."""
    if re.search(r"\bfood\b|do an|an uong|tien an\b", normalized_text):
        return "Food"
    return _budget_category(normalized_text)


_JOB_LOSS = r"lose my job|lost my job|job loss|laid off|unemploy|mat viec|nghi viec|that nghiep"


def _income_loss_months(normalized_text: str) -> int:
    if not re.search(_JOB_LOSS, normalized_text):
        return 0
    m = re.search(r"(\d+)\s*(?:months?|thang)", normalized_text)
    return max(1, min(12, int(m.group(1)))) if m else 3


_CANCEL_FILLER = r"\b(subscription|membership|goi|dich vu|giup toi|giup minh|cho toi|cho minh|please|di|nhe|nha|now)\b"


def _cancel_target(normalized_text: str) -> str:
    for name in _KNOWN_SUB_MERCHANTS:
        if name in normalized_text:
            return "Apple iCloud" if name == "icloud" else name.title()
    m = re.search(r"(?:cancel|huy)\s+(?:my\s+|the\s+)?([a-z ]{2,30})", normalized_text)
    if not m:
        return "unknown"
    return re.sub(r"\s+", " ", re.sub(_CANCEL_FILLER, " ", m.group(1))).strip() or m.group(1).strip()


_KNOWN_SUB_MERCHANTS = ["netflix", "spotify", "apple icloud", "icloud", "california fitness", "coursera", "adobe", "youtube", "chatgpt"]


def _resolve_last_merchant(history: List[dict]) -> Optional[str]:
    """Chỉ truy xuất tên dịch vụ/merchant từ lịch sử gần nhất (không tự suy diễn số tiền/tài khoản)."""
    for turn in reversed((history or [])[-3:]):
        combined = SecurityGuard.normalize_text(f"{turn.get('input', '')} {turn.get('response', '')}")
        found = {("Apple iCloud" if m in ("icloud", "apple icloud") else m.title()) for m in _KNOWN_SUB_MERCHANTS if m in combined}
        if len(found) == 1:
            return found.pop()
        if found:
            return None     # the last turn named several merchants: "cancel that one" is ambiguous, so ask instead of guessing
    return None


class RulePlanner:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def plan(self, text: str, ctx: AgentContext, attachments: Dict[str, bytes],
             history: Optional[List[dict]] = None) -> Plan:
        t = SecurityGuard.normalize_text(text)
        amount = extract_amount(text)
        has_image = bool(attachments)
        last_merchant = _resolve_last_merchant(history or [])

        if re.search(r"\brun my month\b|chay thang|month(ly)? review|close my month", t):
            return Plan("run_my_month", [], "rule")

        m = re.match(r"\s*(?:remember|ghi nho|nho)\s+([a-z_][a-z0-9_]*)\s*[:=]\s*(.+?)\s*$", text, flags=re.I)
        if m:
            return Plan("remember", [PlannedCall("remember", {"key": m.group(1).lower(), "value": m.group(2).strip()})], "rule")
        if re.search(r"what do you remember|do you remember|recall|ban nho gi|nho gi ve toi", t):
            return Plan("recall", [PlannedCall("recall", {})], "rule")

        # "did I pay a scam?" without an amount asks about the past; a message with an amount is a transfer to assess
        if re.search(r"\b(scam|scams|fraud|lua dao|bi lua)\b", t) and not amount:
            return Plan("scan_past_transactions", [PlannedCall("scan_past_transactions", {})], "rule")

        is_question = t.rstrip().endswith("?") or bool(re.search(r"\b(is that|can i|should i|co nen|duoc khong|co du)\b", t))
        is_budget_command = bool(re.search(r"^\s*(?:please\s+)?(set|dat|gioi han|limit|cap)\b.*\b(budget|ngan sach|tran|muc|cap)\b", t)
                                 or re.search(r"\b(budget|ngan sach)\b\s+(?:cho\s+\w+\s+|for\s+\w+\s+)?(?:to|la|bang|=)\s*\d", t))
        if is_budget_command and not is_question and amount:
            cat = _budget_category(t)
            if cat:
                return Plan("set_budget", [PlannedCall("set_budget", {"category": cat, "monthly_cap": amount})], "rule")

        m = re.search(r"(?:what is|what was|explain|why is there|khoan|giao dich)\s+(?:the\s+|this\s+)?(.+?)\s*(?:charge|transaction|payment|la gi|la khoan gi|\?|$)", t)
        if m and re.search(r"charge|transaction|payment|khoan|giao dich|la gi", t) and not (
                re.search(r"\b(chuyen|gui|transfer|send|pay|tra|move)\b", t) and amount):
            query = re.sub(r"^(the|this|that|my)\s+", "", m.group(1).strip())
            if query in ("it", "that", "no", "do") and last_merchant:
                query = last_merchant
            if query:
                return Plan("explain_transaction", [PlannedCall("explain_transaction", {"query": query})], "rule")

        if re.search(r"receipt|hoa don|bill photo", t) and has_image:
            att = next(iter(attachments))
            return Plan("read_receipt", [PlannedCall("read_receipt", {"attachment_id": att})], "rule")

        payee_info = extract_payee(text, ctx)
        # "nap" (top up), "thanh toan", "deposit" move money too; an amount plus an account number is a transfer whatever the verb,
        # so task and deposit scams ("nap 5 trieu de nhan nhiem vu, stk ...") still reach the Guardian
        is_transfer = bool(amount and (re.search(r"\b(chuyen|gui|transfer|send|pay|tra|move|nap|thanh toan|deposit|top up|ck)\b", t)
                                       or payee_info["payee_account"]))
        internal_words = re.search(r"main wallet|vi chinh|emergency|ket|vault|fun wallet|vi vui", t)
        if is_transfer and internal_words and not payee_info["payee_account"]:
            src, dst = "Main Wallet", "Emergency Vault"
            if re.search(r"(from|tu)\s+(the\s+)?(emergency|vault|ket)", t):
                src = "Emergency Vault"
            if re.search(r"(from|tu)\s+(the\s+)?fun", t):
                src = "Fun Wallet"
            if re.search(r"(to|vao|den)\s+(the\s+)?fun", t):
                dst = "Fun Wallet"
            if re.search(r"(to|vao|den)\s+(the\s+)?(main|vi chinh)", t):
                dst = "Main Wallet"
            call = PlannedCall("transfer_internal", {"source": src, "destination": dst, "amount": amount, "note": text})
            return Plan("transfer_internal", [call], "rule")

        if is_transfer:
            base = {**payee_info, "amount": amount, "note": text, "evidence_text": text}
            calls = []
            if has_image:
                att = next(iter(attachments))
                calls.append(PlannedCall("read_chat_screenshot", {"attachment_id": att}))
                base["evidence_image"] = att
            calls.append(PlannedCall("guardian_scan", dict(base)))
            calls.append(PlannedCall("transfer_external", dict(base)))
            return Plan("transfer_external", calls, "rule")

        if has_image:
            # A screenshot with a question but no transfer ("should I pay this?"): read it and assess it, move nothing
            att = next(iter(attachments))
            scan = {**payee_info, "amount": amount or 0.0, "note": text, "evidence_text": text, "evidence_image": att}
            return Plan("scam_check", [PlannedCall("read_chat_screenshot", {"attachment_id": att}),
                                       PlannedCall("guardian_scan", scan)], "rule")

        pronoun_cancel = re.search(r"\b(cancel|huy)\b.*\b(it|that|that one|no|goi do|dich vu do|cai do)\b", t)
        if pronoun_cancel and not last_merchant and _cancel_target(t) in ("it", "that", "that one", "no", "do", "goi do",
                                                                          "dich vu do", "cai do", "unknown", ""):
            return Plan("clarify_cancel", [], "rule")
        if re.search(r"subscription|thue bao|goi dinh ky|recurring|netflix|spotify", t) or (pronoun_cancel and last_merchant):
            if re.search(r"cancel|huy", t):
                merchant = _cancel_target(t)
                if merchant in ("it", "that", "no", "do", "goi do", "dich vu do", "") and last_merchant:
                    merchant = last_merchant
                return Plan("cancel_subscription", [PlannedCall("cancel_subscription", {"merchant": merchant})], "rule")
            return Plan("subscriptions", [PlannedCall("scan_subscriptions", {})], "rule")

        if re.search(r"stress|monte carlo|resilien|shock|survive|" + _JOB_LOSS, t):
            loss = _income_loss_months(t)
            return Plan("stress_test", [PlannedCall("run_stress_test", {"income_loss_months": loss} if loss else {})], "rule")

        if re.search(r"should i buy|co nen mua|buy a|\bmua\b", t) and amount:
            m = re.search(r"(?:buy|mua)\s+(?:a\s+|an\s+|the\s+)?([a-z0-9 ]{2,40}?)(?=\s+for|\s+gia|\s+\d|$)", t)
            item = m.group(1).strip() if m else "item"
            return Plan("second_opinion", [PlannedCall("second_opinion", {"item": item, "price": amount, "justification": text})], "rule")

        if re.search(r"budget|ngan sach|spend|chi tieu|50/30/20|overspend|\btieu\b", t):
            cat = _spend_category(t)
            return Plan("budget_status", [PlannedCall("get_budget_status", {"category": cat} if cat else {})], "rule")

        if re.search(r"wallet|balance|so du|\bvi\b|how much money|money (?:do )?i have|money left|bao nhieu tien|con bao nhieu", t):
            return Plan("wallets", [PlannedCall("get_wallets", {})], "rule")

        return Plan("unknown", [], "rule")


PLANNER_INSTRUCTIONS = ("You are SpendGuard's planner. Choose the minimal sequence of tools to satisfy the user's request. "
                        "Before any transfer_external, call guardian_scan with the same arguments. "
                        "Never invent amounts or account numbers; extract them strictly from the request. Do not call tools for small talk.")


class LLMPlanner:
    """Function-calling planner through the gateway; every plan is validated and falls back to rules."""

    def __init__(self, registry: ToolRegistry, fallback: RulePlanner):
        self.registry = registry
        self.fallback = fallback

    def plan(self, text: str, ctx: AgentContext, attachments: Dict[str, bytes],
             history: Optional[List[dict]] = None) -> Plan:
        if not gateway.available:
            return self.fallback.plan(text, ctx, attachments, history=history)
        untrusted_parts = [Part(kind="text", content=text, source="user")]
        if history:
            hist_str = "\n".join(f"User: {h.get('input', '')}\nAgent: {h.get('response', '')}" for h in history[-3:])
            untrusted_parts.insert(0, Part(kind="text", content=hist_str, source="conversation_history"))
        if attachments:
            untrusted_parts.append(Part(kind="text", source="attachments", content=(
                "Attached images (you cannot see them; read one with read_chat_screenshot or read_receipt): "
                + ", ".join(attachments))))
        res = gateway.generate(text, instructions=PLANNER_INSTRUCTIONS,
                               untrusted=untrusted_parts,
                               tools=self.registry.function_declarations(), purpose="plan")
        if not res.available or not res.function_calls:
            return self.fallback.plan(text, ctx, attachments, history=history)
        calls = [PlannedCall(fc["name"], dict(fc.get("args", {}))) for fc in res.function_calls]
        for c in calls:
            if self.registry.validate(c):
                return self.fallback.plan(text, ctx, attachments, history=history)
        rule_plan = self.fallback.plan(text, ctx, attachments, history=history)
        if rule_plan.intent in ("run_my_month", "scam_check", "remember"):
            # a screenshot is always read and assessed by Guardian, and "remember key: value" is stored exactly as typed
            # (the month review reads those keys), whatever the model chose
            return rule_plan
        if rule_plan.intent in ("transfer_external", "transfer_internal"):
            money = [c for c in calls if c.tool == rule_plan.intent]
            if not money:
                return rule_plan   # a money request must carry its money call so preflight, Guardian and the queue see it
            ref = next(c for c in rule_plan.calls if c.tool == rule_plan.intent)
            for c in money:
                if abs(float(c.args.get("amount", 0)) - float(ref.args.get("amount", 0))) >= 0.5:
                    return rule_plan   # the model may not change the amount the user stated
                if rule_plan.intent == "transfer_internal" and (
                        c.args.get("source") != ref.args.get("source") or c.args.get("destination") != ref.args.get("destination")):
                    return rule_plan
                if rule_plan.intent == "transfer_external":
                    for key in ("payee_account", "bank"):
                        stated = ref.args.get(key) or ""
                        if (c.args.get(key) or "") != stated:
                            return rule_plan   # the model may neither alter nor fabricate payee_account/bank
            rule_tools = {c.tool for c in rule_plan.calls}
            for c in calls:
                if c.tool not in rule_tools and self.registry.get(c.tool).tier(c.args, ctx) != "Tier 1":
                    return rule_plan   # extras the model adds to a money request must be read-only
        intent = rule_plan.intent if rule_plan.intent != "unknown" else calls[0].tool
        return Plan(intent, calls, "llm")


def make_planner(registry: ToolRegistry):
    rule = RulePlanner(registry)
    return LLMPlanner(registry, rule) if gateway.available else rule

