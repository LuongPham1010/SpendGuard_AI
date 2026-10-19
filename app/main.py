"""
FastAPI Server for SpendGuard AI
Shenzhen International FinTech Competition 2026 - WeBank & Tsinghua PBCSF
Topic A: Personal Finance Assistant
"""

import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    BASE_DIR,
    GEMINI_API_KEY,
    DEFAULT_GEMINI_MODEL,
    GEMINI_MODEL_ALIASES,
    DEFAULT_CURRENCY,
    VND_PER_USD,
)
from app.models.schemas import (
    Transaction,
    Wallet,
    WalletTransferRequest,
    WalletTransferResponse,
    DebateRequest,
    DebateResponse,
    MonteCarloRequest,
    MonteCarloResult,
    AntiScamScanRequest,
    AntiScamScanResponse,
    DashboardOverview,
)
from app.core.security import SecurityGuard
from app.core.audit_logger import SandboxAuditLogger
from app.core.notifications import notifications
from app.core.sandbox_wallets import wallet_manager
from app.modules.data_ingestion import DataIngestionEngine
from app.modules.auto_categorizer import AutoCategorizer
from app.modules.ghost_hunter import GhostSubscriptionHunter
from app.modules.debate_arena import FinancialDebateArena
from app.modules.monte_carlo import MonteCarloEngine
from app.modules.anti_scam_shield import AntiScamShield
from app.modules.cashflow_forecaster import CashflowForecaster, CashflowForecastResult
from app.agent.orchestrator import agent, AgentTurn
from app.agent.approvals import approval_queue
from app.agent.memory import profile_store
from app.agent.types import AgentContext
from app.core.llm_gateway import gateway

# Initialize FastAPI App
app = FastAPI(
    title="SpendGuard AI - Autonomous Financial Auditor & Cognitive Fraud Defense",
    version="1.0.0",
    description="2026 Shenzhen International FinTech Competition (WeBank & Tsinghua PBCSF) - Topic A Prototype",
)

# CORS middleware for seamless local and remote testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session transactions
current_transactions: List[Transaction] = []


@app.middleware("http")
async def demo_access_gate(request, call_next):
    """When DEMO_ACCESS_TOKEN is configured (public demo), every request must carry the token.
    Accepted: ?token=..., header X-Demo-Token, or the cookie set after a successful ?token= visit.
    Localhost requests (127.0.0.1, ::1, localhost) are always allowed directly for friction-free local dev."""
    import app.config as cfg
    from starlette.responses import JSONResponse as _JSON
    token = getattr(cfg, "DEMO_ACCESS_TOKEN", "")
    if token:
        client_host = request.client.host if request.client else ""
        if client_host in ("127.0.0.1", "::1", "localhost"):
            return await call_next(request)
        supplied = request.query_params.get("token") or request.headers.get("x-demo-token") or request.cookies.get("spendguard_token")
        if supplied != token:
            return _JSON({"detail": "This demo requires an access token. Open the link with ?token=... once."}, status_code=401)
        response = await call_next(request)
        if request.query_params.get("token") == token:
            response.set_cookie("spendguard_token", token, httponly=True, samesite="lax", max_age=12 * 3600)
        return response
    return await call_next(request)

# Mount static files
static_dir = Path(__file__).resolve().parent / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
async def startup_event():
    """Seed initial transactions from standard 50-item dataset and log initialization"""
    global current_transactions
    try:
        current_transactions = DataIngestionEngine.load_default_transactions()
    except Exception as e:
        print(f"[Startup Warning] Could not load default transactions: {e}")
        current_transactions = []

    SandboxAuditLogger.log_event(
        tier="Tier 1",
        module="SystemInit",
        action="SERVER_STARTUP",
        status="ACTIVE",
        details={
            "initial_transactions_loaded": len(current_transactions),
            "gemini_api_configured": gateway.available,
            "model": DEFAULT_GEMINI_MODEL,
        },
    )


@app.get("/")
async def serve_index():
    """Serve modern 4-Tab Mission Control Single-Page App (index.html)."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"message": "SpendGuard AI API online. Frontend index.html not yet built."})


@app.get("/console")
async def serve_console():
    """Minimal mission-control view of the agent (pipeline rail, conversation, vaults, approvals)."""
    f = static_dir / "index.html"
    if f.exists():
        return FileResponse(f)
    return JSONResponse({"message": "Console not found."}, status_code=404)


@app.get("/legacy")
async def serve_legacy():
    """Alias of the classic full dashboard."""
    legacy_file = static_dir / "legacy.html"
    if legacy_file.exists():
        return FileResponse(legacy_file)
    return JSONResponse({"message": "Legacy dashboard not found."}, status_code=404)


@app.get("/api/health")
async def get_health():
    """Status probe returning Gemini AI connectivity and sandbox state"""
    return {
        "status": "online",
        "competition": "2026 Shenzhen International FinTech Competition (WeBank & Tsinghua PBCSF)",
        "track": "International Track - Topic A: Personal Finance Assistant",
        "gemini_configured": gateway.available,
        "gemini_model": DEFAULT_GEMINI_MODEL,
        "available_models": GEMINI_MODEL_ALIASES,
        "active_currency": DEFAULT_CURRENCY,
        "vnd_to_usd_rate": VND_PER_USD,
        "loaded_transactions_count": len(current_transactions),
        "gemini_keys": len(getattr(gateway.backend, "clients", [])),
        "sandbox": True,
    }


@app.get("/api/dashboard/overview", response_model=DashboardOverview)
async def get_dashboard_overview(month: Optional[str] = Query(None, description="Optional YYYY-MM filter")):
    """Aggregate KPI metrics, 50/30/20 breakdown, and wallet statuses"""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()

    framework_analysis = AutoCategorizer.analyze_spending_framework(current_transactions, month=month)
    framework_analysis["trends"] = AutoCategorizer.compute_multi_month_trends(current_transactions)
    wallets = wallet_manager.get_all_wallets()
    total_balance = sum(w.balance for w in wallets)

    spending_by_category = {
        "Needs": framework_analysis["breakdown"]["Needs"]["amount"],
        "Wants": framework_analysis["breakdown"]["Wants"]["amount"],
        "Savings/Debts": framework_analysis["breakdown"]["Savings"]["amount"],
    }

    recent_txs = list(reversed(current_transactions[-10:]))

    return DashboardOverview(
        total_balance=total_balance,
        total_income_month=framework_analysis["total_income"],
        total_expense_month=framework_analysis["total_expense"],
        savings_rate_pct=framework_analysis["savings_rate_pct"],
        budget_adherence_pct=framework_analysis["adherence_score"],
        wallets=wallets,
        spending_by_category=spending_by_category,
        adherence_50_30_20=framework_analysis,
        recent_transactions=recent_txs,
        gemini_status={
            "enabled": gateway.available,
            "model": DEFAULT_GEMINI_MODEL,
            "fallback_ready": True,
        },
    )


@app.get("/api/dashboard/trends")
async def get_dashboard_trends():
    """Return multi-month 50/30/20 spending trends and month-over-month delta"""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()
    return AutoCategorizer.compute_multi_month_trends(current_transactions)


@app.get("/api/transactions")
async def get_transactions(month: Optional[str] = Query(None)):
    """Return all currently ingested statement transactions (optionally filtered by YYYY-MM)"""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()
    txs = current_transactions
    if month:
        txs = [t for t in current_transactions if str(t.date).startswith(month.strip())]
    return {"count": len(txs), "transactions": txs}


@app.post("/api/transactions/upload")
async def upload_csv_statement(file: UploadFile = File(...)):
    """Upload new bank statement CSV or PDF and update session state"""
    global current_transactions
    content = await file.read()
    fname = (file.filename or "").lower()

    if fname.endswith(".pdf"):
        parsed = DataIngestionEngine.parse_pdf_statement(content, filename=file.filename or "statement.pdf")
    else:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1")
        parsed = DataIngestionEngine.parse_csv(decoded)

    if parsed:
        current_transactions = parsed
        return {
            "success": True,
            "count": len(parsed),
            "transactions": parsed,
            "message": f"Successfully parsed {len(parsed)} transactions."
        }
    else:
        raise HTTPException(status_code=400, detail="Failed to parse valid transactions from uploaded statement.")


@app.post("/api/transactions/upload-pdf")
async def upload_pdf_statement(file: UploadFile = File(...)):
    """Dedicated endpoint to upload and parse PDF bank statements via pdfplumber"""
    global current_transactions
    content = await file.read()
    parsed = DataIngestionEngine.parse_pdf_statement(content, filename=file.filename or "statement.pdf")
    if parsed:
        current_transactions = parsed
        return {
            "success": True,
            "count": len(parsed),
            "transactions": parsed,
            "message": f"Successfully extracted {len(parsed)} transactions from PDF statement.",
        }
    raise HTTPException(status_code=400, detail="Could not extract valid transaction rows from the uploaded PDF.")


@app.post("/api/ocr/receipt")
def upload_receipt_ocr(file: UploadFile = File(...)):
    """Process receipt image using Gemini Multimodal OCR"""
    content = file.file.read()
    filename = file.filename or "receipt.jpg"
    mime_type = file.content_type or "image/jpeg"

    result = DataIngestionEngine.extract_receipt_ocr(content, filename=filename, mime_type=mime_type)
    return result


@app.get("/api/subscriptions")
async def get_subscriptions():
    """Detect ghost recurring subscriptions and annual leakage"""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()

    detected = GhostSubscriptionHunter.detect_subscriptions(current_transactions)
    total_leakage = sum(s.annual_leakage for s in detected)
    active_leakage = sum(s.annual_leakage for s in detected if s.status == "active")
    saved_leakage = sum(s.annual_leakage for s in detected if s.status == "cancelled")
    return {
        "count": len(detected),
        "total_annual_leakage_vnd": total_leakage,
        "active_annual_leakage_vnd": active_leakage,
        "saved_annual_leakage_vnd": saved_leakage,
        "subscriptions": detected,
    }


@app.post("/api/subscriptions/{merchant}/cancel")
async def mark_subscription_cancellation(merchant: str):
    """Tier 2 autonomous action: flag subscription for unsubscribe, record cancellation state and log action"""
    GhostSubscriptionHunter.cancel_subscription(merchant)
    SandboxAuditLogger.log_event(
        tier="Tier 2",
        module="GhostHunter",
        action="SUBSCRIPTION_UNSUBSCRIBE_TRIGGERED",
        status="DISPATCHED",
        details={"merchant": merchant, "channel": "Autonomous Cancellation Notice"},
    )
    return {
        "success": True,
        "tier": "Tier 2",
        "merchant": merchant,
        "status": "FLAGGED_FOR_CANCELLATION",
        "message": f"Autonomous unsubscribe notice synthesized and dispatched for {merchant}.",
    }


@app.get("/api/cashflow/forecast", response_model=CashflowForecastResult)
async def get_cashflow_forecast(days: int = Query(30, ge=7, le=90)):
    """30-day liquidity & cashflow forecast with shortfall warning and Tier 2 recommendation"""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()
    return CashflowForecaster.forecast_30_days(current_transactions, days=days)


@app.post("/api/debate", response_model=DebateResponse)
def run_multi_agent_debate(request: DebateRequest):
    """Run 3-Agent Financial Debate on proposed purchase"""
    return FinancialDebateArena.run_debate(request)


@app.post("/api/monte-carlo", response_model=MonteCarloResult)
async def run_monte_carlo_stress_test(request: MonteCarloRequest):
    """Run 1,000 stochastic Monte Carlo simulations with 3 shocks"""
    return MonteCarloEngine.simulate(request)


@app.post("/api/anti-scam/scan", response_model=AntiScamScanResponse)
async def scan_transfer_for_scams(request: AntiScamScanRequest):
    """Scan recipient note & yield claims for scams and evaluate Tier 3 lockdown"""
    return AntiScamShield.scan_transfer_intent(request)


@app.post("/api/wallets/transfer", response_model=WalletTransferResponse)
async def transfer_between_wallets(request: WalletTransferRequest):
    """Execute internal wallet transfer subject to 3-Tier Security Matrix.
    Override flags sent by the client are ignored: a Tier 3 transfer is approved only through the agent's
    approval queue (one-time code, plus cooling-off and quiz checked on the server when Guardian locked it)."""
    request = request.model_copy(update={"security_override": False, "quiz_passed": False})
    return wallet_manager.execute_transfer(request)


@app.post("/api/wallets/reset")
async def reset_sandbox_wallets():
    """Reset sandbox wallets back to initial benchmark balances (Main 65M, Emergency 120M, Fun 15M)"""
    wallets = wallet_manager.reset_wallets()
    return {
        "success": True,
        "message": "Sandbox wallets reset to initial benchmark balances.",
        "wallets": wallets,
    }


@app.post("/api/wallets/auto-sweep")
async def auto_save_sweep():
    """Autonomous savings sweep from Main Wallet to Emergency Vault based on 50/30/20 gap"""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()

    analysis = AutoCategorizer.analyze_spending_framework(current_transactions)
    sweep_amount = min(5_000_000.0, max(1_000_000.0, analysis["suggested_savings_sweep_vnd"]))

    req = WalletTransferRequest(
        source_wallet="Main Wallet",
        destination_wallet="Emergency Vault",
        amount=sweep_amount,
        note="Autonomous 50/30/20 Emergency Vault Sweep",
        security_override=False,
    )
    response = wallet_manager.execute_transfer(req)
    return response


@app.get("/api/audit-logs")
async def get_audit_logs(limit: int = 50):
    """Retrieve tamper-evident execution logs (Deliverable 06 evidence)"""
    logs = SandboxAuditLogger.get_recent_logs(limit=limit)
    raw_lines = SandboxAuditLogger.get_raw_log_lines(limit=20)
    return {"count": len(logs), "logs": logs, "raw_stream_tail": raw_lines}


@app.get("/api/audit/certificate")
async def get_audit_certificate():
    """Generate a verifiable SHA-256 Compliance & Execution Certificate for judges (Deliverable 06)"""
    logs = SandboxAuditLogger.get_recent_logs(limit=200)
    head_hash = logs[0].trace_hash if logs else "GENESIS_ROOT_SPENDGUARD_2026"
    wallets = wallet_manager.get_all_wallets()
    cert_payload = f"{head_hash}|{len(logs)}|{sum(w.balance for w in wallets)}"
    certificate_signature = hashlib.sha256(cert_payload.encode("utf-8")).hexdigest()

    return {
        "certificate_id": f"SG-2026-{certificate_signature[:10].upper()}",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "competition": "2026 Shenzhen International FinTech Competition (WeBank & Tsinghua PBCSF)",
        "track": "Topic A: Personal Finance Assistant",
        "chain_genesis": "GENESIS_ROOT_SPENDGUARD_2026",
        "chain_head_hash": head_hash,
        "verified_events_count": len(logs),
        "certificate_sha256": certificate_signature,
        "tier_policy": {
            "Tier 1": "Read-Only Autonomous Synthesis",
            "Tier 2": "Controlled Execution <= 5,000,000 VND (Daily Cap 10,000,000 VND)",
            "Tier 3": "Mandatory Human-in-the-Loop & Guardian Cognitive Quiz Lockdown",
        },
        "wallets_snapshot": [w.model_dump() for w in wallets],
        "recent_ledger": [e.model_dump() for e in logs[:100]],
    }


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

@app.post("/api/agent/chat", response_model=AgentTurn)
def agent_chat(text: str = Form(...), session_id: str = Form("default"), files: List[UploadFile] = File(default=[])):
    """Run one agent turn: plan, preflight, execute within tiers, queue high-risk actions, reflect."""
    global current_transactions
    if not current_transactions:
        current_transactions = DataIngestionEngine.load_default_transactions()
    attachments = {}
    for f in files:
        attachments[f.filename or f"file{len(attachments)}"] = f.file.read()
    return agent.run_turn(session_id, text, attachments, current_transactions)


@app.get("/api/agent/approvals")
async def agent_approvals():
    """Pending human-in-the-loop requests plus decided history."""
    return {"pending": [r.model_dump() for r in approval_queue.list("PENDING")],
            "history": [r.model_dump() for r in approval_queue.list("APPROVED")]
                       + [r.model_dump() for r in approval_queue.list("REJECTED")]}


@app.post("/api/agent/approvals/{request_id}/otp")
def agent_issue_otp(request_id: str):
    """Issue a one-time approval code. Sandbox: the code is returned as a simulated SMS instead of being sent."""
    out = approval_queue.issue_otp(request_id)
    if out.get("status") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=out["message"])
    return out


@app.post("/api/agent/approvals/{request_id}/decide")
def agent_decide(request_id: str, approve: bool = Body(..., embed=True),
                       quiz_answers: Optional[List[int]] = Body(None, embed=True),
                       otp: Optional[str] = Body(None, embed=True)):
    """Approve or reject a queued action. Approval needs the one-time code; LOCKED actions also need cooling-off and quiz."""
    ctx = AgentContext(session_id="approval", transactions=current_transactions, profile=profile_store.load(), flags=[])
    out = approval_queue.decide(request_id, approve, quiz_answers, ctx, agent.preflight, agent.executor, otp=otp)
    if out.get("result") is not None:
        out["result"] = asdict(out["result"])
    return out


@app.get("/api/notifications")
async def list_notifications(limit: int = Query(20, ge=1, le=100)):
    """Notifications for actions taken on the user's behalf (simulated push in the sandbox)."""
    return {"unread": notifications.unread(), "items": notifications.list(limit)}


@app.post("/api/notifications/read")
async def read_notifications():
    notifications.mark_all_read()
    return {"unread": 0}


@app.get("/api/agent/quiz")
async def agent_quiz():
    """Cognitive safety quiz without the answer key."""
    return {"questions": [{"id": q.id, "question": q.question, "options": q.options} for q in AntiScamShield.COGNITIVE_QUIZ]}
