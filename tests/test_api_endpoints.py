"""
Integration Tests for FastAPI Endpoints using TestClient
"""

import io
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestApiEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def tearDown(self):
        import app.main
        from app.modules.data_ingestion import DataIngestionEngine
        app.main.current_transactions = DataIngestionEngine.load_default_transactions()

    def test_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["gemini_model"], "gemini-3.8-flash")
        self.assertIn("gemini-3.8-flash", data["available_models"])

    def test_dashboard_overview(self):
        res = self.client.get("/api/dashboard/overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_balance", data)
        self.assertIn("wallets", data)
        self.assertEqual(len(data["wallets"]), 3)
        self.assertIn("adherence_50_30_20", data)

    def test_transactions_endpoint(self):
        res = self.client.get("/api/transactions")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["count"], 50)

    def test_statement_upload_endpoint(self):
        csv_data = (
            "id,date,description,amount,type,category,subcategory,wallet\n"
            "TX_UP1,2026-10-10,Luong chuyen khoan Cong ty,40000000,inflow,Income,Salary,Main Wallet\n"
            "TX_UP2,2026-10-11,Tien nha thang 10,8000000,outflow,Needs,Housing,Main Wallet\n"
        )
        files = {"file": ("test_statement.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res = self.client.post("/api/transactions/upload", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 2)

    def test_subscriptions_endpoint_and_cancellation(self):
        # 1. Query subscriptions
        res = self.client.get("/api/subscriptions")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("subscriptions", data)

        # 2. Cancel a subscription
        res_cancel = self.client.post("/api/subscriptions/Spotify/cancel")
        self.assertEqual(res_cancel.status_code, 200)
        self.assertEqual(res_cancel.json()["status"], "FLAGGED_FOR_CANCELLATION")

        # 3. Verify updated stats
        res_after = self.client.get("/api/subscriptions")
        data_after = res_after.json()
        self.assertIn("saved_annual_leakage_vnd", data_after)
        self.assertIn("active_annual_leakage_vnd", data_after)

    def test_debate_endpoint(self):
        payload = {
            "item_name": "iPhone 16 Pro Max",
            "price": 34990000.0,
            "user_income": 35000000.0,
            "user_justification": "Upgrade for work"
        }
        res = self.client.post("/api/debate", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("verdict", data)
        self.assertEqual(len(data["turns"]), 3)

    def test_monte_carlo_endpoint(self):
        payload = {
            "initial_savings": 50000000.0,
            "monthly_income": 35000000.0,
            "monthly_expenses": 22000000.0,
            "num_simulations": 500,
            "months": 12
        }
        res = self.client.post("/api/monte-carlo", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("resilience_score", data)
        self.assertEqual(len(data["percentile_10"]), 13)

    def test_anti_scam_scan_endpoint(self):
        payload = {
            "recipient_name": "Scam Bot",
            "recipient_account": "111222333",
            "bank_name": "FakeBank",
            "amount": 25000000.0,
            "transfer_note": "Chuyen gap trong 15 phut lai 3% ngay",
            "advertised_yield_daily_pct": 3.0,
            "source_context": "Telegram group"
        }
        res = self.client.post("/api/anti-scam/scan", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["is_locked"])
        self.assertEqual(len(data["cognitive_quiz"]), 3)

    def test_wallet_transfer_tier3_flow(self):
        # 1. Transfer > 5M without override is held
        held_payload = {
            "source_wallet": "Main Wallet",
            "destination_wallet": "Emergency Vault",
            "amount": 8_000_000.0,
            "note": "Large reserve transfer",
            "security_override": False
        }
        res_held = self.client.post("/api/wallets/transfer", json=held_payload)
        self.assertEqual(res_held.status_code, 200)
        self.assertEqual(res_held.json()["status"], "HELD_FOR_APPROVAL")

        # 2. Override flags sent by the client cannot release a Tier 3 transfer
        forced_payload = {
            "source_wallet": "Main Wallet",
            "destination_wallet": "Emergency Vault",
            "amount": 8_000_000.0,
            "note": "Large reserve transfer",
            "security_override": True,
            "quiz_passed": True
        }
        res_forced = self.client.post("/api/wallets/transfer", json=forced_payload)
        self.assertEqual(res_forced.status_code, 200)
        self.assertEqual(res_forced.json()["status"], "HELD_FOR_APPROVAL")

    def test_wallets_auto_sweep_endpoint(self):
        res = self.client.post("/api/wallets/auto-sweep")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["tier"], "Tier 2")

    def test_audit_logs_endpoint(self):
        self.client.get("/api/dashboard/overview")  # produces at least one audit event
        res = self.client.get("/api/audit-logs")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)
        self.assertIn("logs", data)

    def test_frontend_index_served(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("SpendGuard AI", res.text)


if __name__ == "__main__":
    unittest.main()
