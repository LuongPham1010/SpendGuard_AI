"""Session memory (process) and the persisted user profile (JSON)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.config import MEMORY_PATH


class PayeeRecord(BaseModel):
    name: str
    account_masked: str
    first_seen: str
    count: int = 1
    bank: str = ""


class UserProfile(BaseModel):
    monthly_income: float = 35_000_000.0
    budgets: Dict[str, float] = Field(default_factory=lambda: {"Dining": 4_000_000.0, "Shopping": 2_000_000.0})
    known_payees: Dict[str, PayeeRecord] = Field(default_factory=dict)
    trusted_contact: str = "Family member"
    facts: Dict[str, str] = Field(default_factory=dict)
    approval_history: List[dict] = Field(default_factory=list)
    cooling_off_until: Optional[str] = None


def mask_account(account: str) -> str:
    """Mask any bare account number for logs and responses (keeps 3+3 digits when long enough)."""
    account = str(account or "")
    return f"{account[:3]}****{account[-3:]}" if len(account) >= 8 else ("****" if account else "")


_mask = mask_account


class ProfileStore:
    def __init__(self, path: Path = MEMORY_PATH):
        self.path = Path(path)

    def load(self) -> UserProfile:
        if self.path.exists():
            try:
                return UserProfile(**json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return UserProfile()

    def save(self, profile: UserProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    def is_new_payee(self, profile: UserProfile, account: str) -> bool:
        return account not in profile.known_payees

    def record_payee(self, profile: UserProfile, name: str, account: str, bank: str = "") -> None:
        if account in profile.known_payees:
            profile.known_payees[account].count += 1
            if bank and not profile.known_payees[account].bank:
                profile.known_payees[account].bank = bank
        else:
            profile.known_payees[account] = PayeeRecord(
                name=name, account_masked=_mask(account),
                first_seen=datetime.now(timezone.utc).isoformat(),
                bank=bank)
        self.save(profile)


class SessionMemory:
    def __init__(self):
        self._turns: Dict[str, List[dict]] = {}

    def add_turn(self, session_id: str, turn: dict) -> None:
        self._turns.setdefault(session_id, []).append(turn)

    def history(self, session_id: str, n: int = 5) -> List[dict]:
        return self._turns.get(session_id, [])[-n:]


profile_store = ProfileStore()
session_memory = SessionMemory()
