"""Guardian: scam risk assessment from rule, behavioral and (optional) LLM signals, with intervention output."""
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.agent.types import AgentContext
from app.config import BASE_DIR, DEMO_COOLING_OFF_SECONDS, GUARDIAN_LOCK_THRESHOLD
from app.core.audit_logger import SandboxAuditLogger
from app.core.llm_gateway import gateway, Part
from app.core.sandbox_wallets import wallet_manager
from app.core.security import SecurityGuard
from app.modules.anti_scam_shield import AntiScamShield
from app.agent.memory import mask_account
from app.modules.payee_reputation import payee_reputation as _default_reputation

payee_reputation = _default_reputation   # module attribute so tests can swap providers

WEIGHTS_PATH = Path(__file__).resolve().parent / "guardian_weights.json"
COUNTER_FACTS_PATH = BASE_DIR / "data" / "guardian" / "counter_facts.json"

RULES = {
    "authority_impersonation": r"cong an|canh sat|vien kiem sat|toa an|police|prosecutor|court|dieu tra|lenh bat|investigation|arrest warrant|ngan hang nha nuoc|bo cong an|xu ly vi pham|xac minh thong tin|phat nguoi|no cuoc|cat dien|khoa hai chieu|dinh danh muc|app dich vu cong|link dich vu cong|bao hiem xa hoi|can bo thu ly|visual_cue:\s*authority_impersonation",
    "urgency": r"\bgap\b|khan cap|ngay lap tuc|ngay bay gio|trong \d+ phut|urgent|immediately|right now|within \d+ minutes|act now|het han hom nay",
    "secrecy": r"bi mat|khong noi voi ai|khong duoc noi|dung noi|giu kin|secret|do not tell|don't tell|keep this between",
    "safe_account": r"tai khoan an toan|tai khoan tam giu|tam giu|xac minh tai khoan|safe account|custody account|holding account|temporary custody|verify your account|verification account|tai khoan .{0,25}bi (?:dong bang|phong toa|tam khoa)|(?:de|giup) mo (?:lai|khoa) tai khoan|account (?:is |has been |was )?(?:frozen|suspended)|(?:to )?unfreeze your account",
    "task_scheme": r"nhiem vu|lam nhiem vu|hoa hong|commission|complete \d+ \w* ?tasks|product tasks|nap tien de rut|nap them|deposit to (?:withdraw|unlock)|unlock withdrawal|telegram vip|vip telegram|telegram group|chuyen gia doc lenh|guaranteed? (?:return|profit|yield|passive)|zero risk|bao hiem von|cam ket loi nhuan|cong tac vien|viec nhe luong cao|chot don|bao lo|win rate|mentor group|loi nhuan \d+% moi thang|profit cycle|\b\d+x (?:back|return|your money)|(?:double|triple) your (?:money|investment)|nhan (?:lai|ve) gap (?:\d+|doi|ba) lan|x\d+ (?:von|tai khoan)",
    "prize": r"trung thuong|giai thuong|lottery|prize|you have won|phi nhan thuong|claim your reward",
    "otp_request": r"\botp\b|ma xac thuc|ma xac nhan|doc ma|send the code|verification code|\bpin\b|mat khau",
    "romance": r"anh yeu|em yeu|my love|darling|honey|chua gap mat|never met|quan tai|ket hon|gift stuck",
    "customs_fee": r"hai quan|phi thong quan|customs|shipping fee|courier fee|phi van chuyen|goi hang bi giu",
    "refund_scam": r"nhan hoan tien|hoan tien|refund department|processing fee to this account|phi cap nhat|overcharged|receive your .{0,20}refund",
    "relative_emergency": r"con dang cap cuu|dang cap cuu|doi so dien thoai|this is my new number|lost my phone|ket tien gap|sep day|dang hop khong nghe may|hoan lai sau|chuyen cho doi tac|me oi con day|bo oi con day|con day con doi|new number.{0,40}(?:send|transfer|need)",
    "fake_receipt": r"bien lai chuyen khoan gia|bien lai gia|ngan hang dang treo|transfer on hold|release fee|phi kich hoat|chua can xem|khong ship cod|day la bien lai.{0,40}(?:treo|phi|chuyen lai)|the money arrives|visual_cue:\s*fake_receipt",
}
PONZI = r"(\d+(?:[.,]\d+)?)\s*%[a-z\s]{0,20}?(?:moi ngay|mot ngay|hang ngay|/\s*ngay|per day|a day|each day|daily|/\s*day|\bngay\b)"


class TransferIntent(BaseModel):
    amount: float
    payee_name: str = ""
    payee_account: str = ""
    bank: str = ""
    note: str = ""


class Evidence(BaseModel):
    text: str = ""
    image_text: str = ""


class GuardianResult(BaseModel):
    risk_score: float
    level: str
    locked: bool
    features: Dict[str, float]
    evidence: List[str] = Field(default_factory=list)
    scam_type: Optional[str] = None
    counter_facts: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    cooling_off_seconds: int = 0
    quiz: List[dict] = Field(default_factory=list)
    llm_used: bool = False
    amount: float = 0.0
    payee_account: str = ""


def _load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


class Guardian:
    @staticmethod
    def has_content_cue(features: Dict[str, float]) -> bool:
        """A lock needs something in the content: a rule match, Ponzi math, or a blocklisted payee."""
        return (any(features.get(k, 0.0) >= 1.0 for k in RULES) or features.get("ponzi_math", 0.0) >= 1.0
                or features.get("payee_blacklisted", 0.0) >= 1.0)

    @staticmethod
    def rule_features(text: str) -> Dict[str, float]:
        text = (text or "").replace("gặp", "meet").replace("Gặp", "meet").replace("GẶP", "meet")   # 'met' is not 'urgent'
        t = SecurityGuard.normalize_text(text)
        f = {k: (1.0 if re.search(p, t) else 0.0) for k, p in RULES.items()}
        m = re.search(PONZI, t)
        f["ponzi_math"] = float(m.group(1).replace(",", ".")) if m else 0.0
        return f

    @staticmethod
    def behavior_features(intent: TransferIntent, ctx: AgentContext) -> Dict[str, float]:
        profile = ctx.profile
        known = getattr(profile, "known_payees", {}) if profile is not None else {}
        new = 1.0 if (intent.payee_account and intent.payee_account not in known) else 0.0
        outflows = [t.amount for t in ctx.transactions if getattr(t, "type", "") == "outflow"]
        avg = (sum(outflows) / len(outflows)) if outflows else 2_000_000.0
        ratio = min(10.0, intent.amount / max(avg, 1.0)) / 10.0
        vault = wallet_manager.get_wallet("emergency")
        main = wallet_manager.get_wallet("main")
        liquid = main.balance if main else 0.0
        drains = 0.0
        if vault and intent.amount > liquid:
            drains = min(1.0, (intent.amount - liquid) / max(vault.balance, 1.0))
        hour = datetime.now().hour
        unusual = 1.0 if (hour >= 22 or hour < 6) else 0.0
        now_ts = datetime.now().timestamp()
        recent = 0
        for entry in SandboxAuditLogger.get_recent_logs(200):
            if entry.module != "Guardian":
                continue
            try:
                if now_ts - datetime.fromisoformat(entry.timestamp).timestamp() < 3600:
                    recent += 1
            except Exception:
                continue
        velocity = min(1.0, recent / 5.0)
        round_large = 1.0 if (intent.amount >= 20_000_000 and intent.amount % 1_000_000 == 0) else 0.0
        rep = payee_reputation.lookup(intent.payee_account, intent.bank) if intent.payee_account else {"status": "unknown"}
        blacklisted = 1.0 if rep.get("status") == "blacklisted" else 0.0
        return {"payee_is_new": new, "amount_ratio_30d": ratio, "drains_vault": drains,
                "unusual_hour": unusual, "velocity": velocity, "round_large": round_large,
                "payee_blacklisted": blacklisted}

    @staticmethod
    def score(features: Dict[str, float]) -> float:
        cfg = _load_json(WEIGHTS_PATH, {"weights": {}, "bias": -4.0, "threshold": 80.0})
        z = cfg["bias"]
        for k, w in cfg["weights"].items():
            v = features.get(k, 0.0)
            if k == "ponzi_math":
                v = min(v, 5.0)
            z += w * v
        return round(100.0 / (1.0 + math.exp(-z)), 1)

    @staticmethod
    def scam_type_from(features: Dict[str, float]) -> Optional[str]:
        if features.get("payee_blacklisted", 0.0) >= 1.0:
            return "reported_account"
        order = ["authority_impersonation", "otp_request", "task_scheme", "prize", "romance", "customs_fee", "safe_account",
                 "refund_scam", "relative_emergency", "fake_receipt"]
        for k in order:
            if features.get(k, 0.0) >= 1.0:
                return "investment_ponzi" if k == "task_scheme" else k
        if features.get("ponzi_math", 0.0) >= 1.0:
            return "investment_ponzi"
        return None

    @staticmethod
    def _llm_judgment(text: str) -> Dict[str, Any]:
        if not gateway.available or not text.strip():
            return {"confidence": 0.0, "quotes": [], "used": False}
        res = gateway.generate(
            "Decide whether the message is a financial scam. Return JSON {\"is_scam\": bool, \"confidence\": 0..1, "
            "\"scam_type\": str, \"evidence_quotes\": [str]}. Quotes must be exact substrings.",
            instructions="You are a fraud analyst for Southeast Asian consumer scams.",
            untrusted=[Part(kind="text", content=text, source="evidence")], schema={"type": "object"}, purpose="guardian_judgment")
        data = res.data or {}
        quotes = [q for q in data.get("evidence_quotes", []) if isinstance(q, str) and q in text]
        conf = float(data.get("confidence", 0.0)) if data.get("is_scam") else 0.0
        return {"confidence": max(0.0, min(1.0, conf)), "quotes": quotes, "used": True}

    @classmethod
    def content_risk(cls, text: str) -> Dict[str, Any]:
        """Content-only score for a payment that already left the account: rules and Ponzi math, no behaviour
        signals, no model call and no audit entry (a statement scan would otherwise flood the velocity feature)."""
        features = cls.rule_features(text)
        risk = cls.score(features)
        threshold = _load_json(WEIGHTS_PATH, {}).get("threshold", GUARDIAN_LOCK_THRESHOLD)
        return {"risk_score": risk, "suspicious": risk >= threshold and cls.has_content_cue(features),
                "scam_type": cls.scam_type_from(features),
                "matched": [k for k in RULES if features.get(k, 0.0) >= 1.0],
                "ponzi_daily_pct": features["ponzi_math"]}

    @classmethod
    def assess(cls, intent: TransferIntent, evidence: Evidence, ctx: AgentContext) -> GuardianResult:
        text = " ".join(x for x in [intent.note, evidence.text, evidence.image_text] if x)
        features = cls.rule_features(text)
        features.update(cls.behavior_features(intent, ctx))
        judgment = cls._llm_judgment(text)
        features["llm_confidence"] = judgment["confidence"]
        risk = cls.score(features)
        threshold = _load_json(WEIGHTS_PATH, {}).get("threshold", GUARDIAN_LOCK_THRESHOLD)
        strong_llm = features["llm_confidence"] >= 0.9 and bool(judgment["quotes"])    # the model must be sure and point at words
        content_cue = cls.has_content_cue(features) or strong_llm
        locked = risk >= threshold and content_cue
        level = "CRITICAL" if locked else "HIGH" if risk >= 50 else "MEDIUM" if risk >= 25 else "LOW"
        scam_type = cls.scam_type_from(features)
        ev = [f"Matched pattern '{k}'" for k, v in features.items() if k in RULES and v >= 1.0]
        if features["ponzi_math"] >= 1.0:
            apy = ((1 + features["ponzi_math"] / 100) ** 365 - 1) * 100
            apy_txt = f"{apy:,.0f}%" if apy < 1e6 else "more than 1,000,000%"   # beyond that the digits stop meaning anything
            ev.append(f"Advertised {features['ponzi_math']}%/day compounds to {apy_txt} per year")
        if features["payee_is_new"]:
            ev.append("Payee account has never been paid before")
        if features.get("payee_blacklisted"):
            rep = payee_reputation.lookup(intent.payee_account, intent.bank)
            ev.append(f"Payee account is on the scam blocklist ({rep.get('label', 'reported')}; source: {rep.get('source', 'n/a')})")
        if features["drains_vault"] > 0:
            ev.append(f"Transfer would consume {features['drains_vault']*100:.0f}% of the Emergency Vault")
        ev += [f"Evidence quote: \"{q}\"" for q in judgment["quotes"]]
        cf_all = _load_json(COUNTER_FACTS_PATH, {})
        counter = list(cf_all.get(scam_type or "", [])) + list(cf_all.get("generic", []))
        trusted = getattr(ctx.profile, "trusted_contact", "family") if ctx.profile is not None else "family"
        if locked:
            actions = ["Transfer frozen in the sandbox",
                       f"Cooling-off period of {DEMO_COOLING_OFF_SECONDS} seconds started",
                       f"Notice sent to trusted contact ({trusted}) [simulated]",
                       "Answer the 3-question safety quiz to unlock"]
        elif risk >= 50:
            actions = ["Verify the payee through an official channel before approving"]
        else:
            actions = ["No action required"]
        result = GuardianResult(risk_score=risk, level=level, locked=locked, features=features, evidence=ev,
                                scam_type=scam_type, counter_facts=counter, recommended_actions=actions,
                                cooling_off_seconds=DEMO_COOLING_OFF_SECONDS if locked else 0,
                                quiz=[q.model_dump(exclude={"correct_option_index"}) for q in AntiScamShield.COGNITIVE_QUIZ]
                                     if locked else [],                     # the answer key stays on the server
                                llm_used=judgment["used"], amount=float(intent.amount), payee_account=intent.payee_account or "")
        SandboxAuditLogger.log_event(tier="Tier 3" if locked else "Tier 1", module="Guardian", action="SCAM_ASSESSMENT",
                                     status="LOCKDOWN_ENFORCED" if locked else level,
                                     details={"risk_score": risk, "scam_type": scam_type, "amount": intent.amount,
                                              "payee": mask_account(intent.payee_account), "llm_used": judgment["used"]})
        return result