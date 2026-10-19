"""
Configuration for SpendGuard AI
Shenzhen International FinTech Competition 2026 - WeBank & Tsinghua PBCSF
Topic A: Personal Finance Assistant
"""

import os
from pathlib import Path
from typing import List

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file if present in project directory
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

# Gemini AI Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
# Optional shared secret for a public demo URL: when set, the UI and API require ?token=, X-Demo-Token or the cookie
DEMO_ACCESS_TOKEN = os.getenv("DEMO_ACCESS_TOKEN", "")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Optional extra keys for rotation on quota/capacity errors (comma-separated)
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
# Gemini model preference: defaults to Gemini 3.8 Flash as requested, with fallback aliases
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Fallback chain, verified against the live API on 2026-10-13 (2.5/2.0 models now return 404 and were removed)
GEMINI_MODEL_ALIASES = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
]

# LLM provider: "gemini" when a key is present and the SDK is installed, else "none"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini" if GEMINI_API_KEY else "none")


# Fallback mode toggle: if True, gracefully falls back to deterministic heuristic engines
# when API keys are not provided, rate limited, or network is offline.
FALLBACK_TO_MOCK = os.getenv("FALLBACK_TO_MOCK", "true").lower() in ("1", "true", "yes")

# Currency Settings
DEFAULT_CURRENCY = "VND"
VND_PER_USD = float(os.getenv("VND_PER_USD", "25400.0"))

# Budget Framework (50/30/20 Rule)
BUDGET_TARGET_NEEDS_PCT = 0.50
BUDGET_TARGET_WANTS_PCT = 0.30
BUDGET_TARGET_SAVINGS_PCT = 0.20

# 3-Tier Security Thresholds (VND)
TIER1_MAX_LIMIT_VND = 0.0               # Read-only, no state mutation
TIER2_MAX_LIMIT_VND = 5_000_000.0       # Up to 5M VND: Controlled Auto execution (internal transfers/savings)
TIER3_MIN_LIMIT_VND = 5_000_000.0
TIER2_DAILY_CAP_VND = 10_000_000.0     # Autonomous Tier 2 money movement allowed per day       # >= 5M VND: Mandatory Human-in-the-Loop approval

# Cognitive Anti-Scam Shield Settings
SCAM_CRITICAL_RISK_THRESHOLD = 80.0    # Risk score > 80 locks transfer
SCAM_COOLING_OFF_MINUTES = 60          # 60-minute mandatory reflection period
PONZI_DAILY_YIELD_THRESHOLD_PCT = 1.0  # Daily yield > 1.0% flagged as Ponzi scheme
GUARDIAN_LOCK_THRESHOLD = 80.0
PLANNER_MAX_CALLS = 6
MAX_ITERATIONS = 5                 # plan / replan rounds per turn (the agent uses 2: plan, then one replan)
CIRCUIT_BREAKER_ERRORS = 2         # consecutive tool errors that stop the rest of the turn
DEMO_COOLING_OFF_SECONDS = int(os.getenv("DEMO_COOLING_OFF_SECONDS", "60"))

# Paths to data and logs
DEFAULT_TRANSACTIONS_CSV = DATA_DIR / "sample_transactions_50.csv"
EXECUTION_LOG_FILE = LOGS_DIR / "sandbox_execution.log"
MEMORY_PATH = DATA_DIR / "memory" / "profile.json"
