"""Tests for new upgrades: 30-day Cashflow Forecaster, PDF statement parsing, and new API endpoints."""
import io
import pytest
import pymupdf
from fastapi.testclient import TestClient
from app.main import app
from app.models.schemas import Transaction
from app.modules.cashflow_forecaster import CashflowForecaster
from app.modules.data_ingestion import DataIngestionEngine


def test_cashflow_forecaster_30_days():
    txs = [
        Transaction(id="t1", date="2026-09-01", description="Salary", amount=35_000_000.0, category="Income", type="inflow"),
        Transaction(id="t2", date="2026-09-03", description="Rent", amount=8_500_000.0, category="Housing", type="outflow"),
        Transaction(id="t3", date="2026-09-10", description="Netflix", amount=260_000.0, category="Subscription", type="outflow"),
        Transaction(id="t4", date="2026-09-15", description="Groceries", amount=1_500_000.0, category="Groceries", type="outflow"),
    ]
    res = CashflowForecaster.forecast_30_days(txs, days=30)
    assert res.starting_main_balance > 0
    assert len(res.projections) == 30
    assert res.daily_burn_rate >= 0
    assert isinstance(res.shortfall_detected, bool)


def test_api_cashflow_forecast_endpoint():
    with TestClient(app) as c:
        res = c.get("/api/cashflow/forecast?days=30")
        assert res.status_code == 200
        data = res.json()
        assert "starting_main_balance" in data
        assert "projections" in data
        assert len(data["projections"]) == 30


def test_api_wallets_reset_endpoint():
    with TestClient(app) as c:
        res = c.post("/api/wallets/reset")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "wallets" in data


def test_api_compliance_certificate_endpoint():
    with TestClient(app) as c:
        res = c.get("/api/audit/certificate")
        assert res.status_code == 200
        data = res.json()
        assert "certificate_sha256" in data
        assert "certificate_id" in data
        assert data["verified_events_count"] >= 0


def test_parse_real_pdf_statement_with_pymupdf():
    """Verify PyMuPDF statement parser on an in-memory generated bank statement."""
    doc = pymupdf.open()
    page = doc.new_page()

    # Draw bank statement content
    page.insert_text((50, 50), "VIETCOMBANK OFFICIAL STATEMENT - 2026", fontsize=14)
    page.insert_text((50, 90), "2026-09-01 | CT LUONG THANG 9 CONG TY FINTECH | 35,000,000", fontsize=10)
    page.insert_text((50, 115), "2026-09-03 | TIEN THUE NHA VINHOMES CENTRAL PARK | -8,500,000", fontsize=10)
    page.insert_text((50, 140), "2026-09-10 | THANH TOAN NETFLIX PREMIUM HANG THANG | -260,000", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()

    txs = DataIngestionEngine.parse_pdf_statement(pdf_bytes, filename="vcb_statement.pdf")
    assert len(txs) >= 3

    desc_all = " ".join(t.description for t in txs)
    assert "LUONG THANG" in desc_all
    assert "VINHOMES" in desc_all
    assert "NETFLIX" in desc_all

    # Verify auto-categorization and subscription detection
    sub_tx = next((t for t in txs if "NETFLIX" in t.description), None)
    assert sub_tx is not None
    assert sub_tx.is_subscription is True
