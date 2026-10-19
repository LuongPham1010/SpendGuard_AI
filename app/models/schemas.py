"""
Data schemas for SpendGuard AI
Using Pydantic v2 / v1 compatible definitions
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Transaction(BaseModel):
    id: str
    date: str
    description: str
    amount: float
    type: str  # "inflow" | "outflow"
    category: str  # "Needs" | "Wants" | "Savings/Debts" | "Income"
    subcategory: str = "General"
    wallet: str = "Main Wallet"
    is_subscription: bool = False
    merchant: Optional[str] = None
    raw_details: Optional[str] = None


class Wallet(BaseModel):
    id: str
    name: str
    balance: float
    currency: str = "VND"
    description: str = ""
    color: str = "blue"
    icon: str = "wallet"


class WalletTransferRequest(BaseModel):
    source_wallet: str
    destination_wallet: str
    amount: float
    note: str = ""
    security_override: bool = False
    quiz_passed: bool = False


class WalletTransferResponse(BaseModel):
    success: bool
    tier: str
    status: str  # "EXECUTED" | "HELD_FOR_APPROVAL" | "REJECTED"
    message: str
    source_wallet: str
    destination_wallet: str
    amount: float
    new_source_balance: Optional[float] = None
    new_dest_balance: Optional[float] = None
    trace_id: str


class SubscriptionDetection(BaseModel):
    merchant: str
    amount: float
    frequency_days: float
    occurrences: int
    last_charged: str
    annual_leakage: float
    unsubscribe_url: str
    email_template_en: str
    email_template_vi: str
    status: str = "active"  # "active" | "flagged_to_cancel" | "cancelled"


class DebateRequest(BaseModel):
    item_name: str
    price: float
    user_income: Optional[float] = 35_000_000.0
    category: str = "Wants"
    user_justification: str = ""


class DebateTurn(BaseModel):
    agent: str  # "Optimist" | "Risk Auditor" | "Arbiter"
    avatar: str
    stance: str  # "SUPPORT" | "OPPOSE" | "VERDICT"
    message: str
    arguments: List[str] = []


class DebateResponse(BaseModel):
    item_name: str
    price: float
    verdict: str  # "APPROVED" | "DENIED" | "DELAYED" | "CONDITIONAL_APPROVAL"
    confidence_score: float
    executive_summary: str
    turns: List[DebateTurn]
    action_plan: List[str]


class MonteCarloRequest(BaseModel):
    initial_savings: float = 50_000_000.0
    monthly_income: float = 35_000_000.0
    monthly_expenses: float = 22_000_000.0
    num_simulations: int = 1000
    months: int = 12
    income_shock_prob: float = 0.10
    emergency_shock_min: float = 5_000_000.0
    emergency_shock_max: float = 20_000_000.0
    inflation_rate: float = 0.10
    income_loss_months: int = 0          # scenario: no income at all for the first N months (job loss)


class MonteCarloResult(BaseModel):
    months: List[str]
    percentile_10: List[float]
    percentile_50: List[float]
    percentile_90: List[float]
    resilience_score: float  # 0 to 100
    bankruptcy_probability: float  # Percentage
    recommended_emergency_buffer: float
    analysis_summary: str


class QuizQuestion(BaseModel):
    id: int
    question: str
    options: List[str]
    correct_option_index: int
    explanation: str


class AntiScamScanRequest(BaseModel):
    recipient_name: str
    recipient_account: str
    bank_name: str
    amount: float
    transfer_note: str
    advertised_yield_daily_pct: float = 0.0
    source_context: str = ""


class AntiScamScanResponse(BaseModel):
    risk_score: float  # 0 to 100
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    is_locked: bool  # True if risk > 80
    urgency_detected: bool
    manipulation_tactics: List[str]
    ponzi_math_flag: bool
    cooling_off_minutes: int
    cognitive_quiz: List[QuizQuestion]
    explanation: str
    tier: str


class AuditLogEntry(BaseModel):
    id: str
    timestamp: str
    tier: str
    module: str
    action: str
    status: str
    details: Dict[str, Any]
    trace_hash: str


class DashboardOverview(BaseModel):
    total_balance: float
    total_income_month: float
    total_expense_month: float
    savings_rate_pct: float
    budget_adherence_pct: float
    wallets: List[Wallet]
    spending_by_category: Dict[str, float]
    adherence_50_30_20: Dict[str, Any]
    recent_transactions: List[Transaction]
    gemini_status: Dict[str, Any]
