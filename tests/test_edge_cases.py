"""
Edge Case Tests for SpendGuard AI
Tests boundary limits, empty inputs, extreme shock rates, and security enforcement
"""

import unittest
from app.core.security import SecurityGuard
from app.core.sandbox_wallets import wallet_manager
from app.models.schemas import WalletTransferRequest, MonteCarloRequest, AntiScamScanRequest
from app.modules.monte_carlo import MonteCarloEngine
from app.modules.anti_scam_shield import AntiScamShield
from app.modules.data_ingestion import DataIngestionEngine


class TestEdgeCases(unittest.TestCase):

    def test_tier_boundary_exactly_5m_vnd(self):
        # Exactly 5M VND is Tier 2
        t2 = SecurityGuard.evaluate_tier("INTERNAL_TRANSFER", amount=5_000_000.0)
        self.assertEqual(t2["tier"], "Tier 2")
        self.assertFalse(t2["requires_human_approval"])

        # 5M + 1 VND is Tier 3
        t3 = SecurityGuard.evaluate_tier("INTERNAL_TRANSFER", amount=5_000_001.0)
        self.assertEqual(t3["tier"], "Tier 3")
        self.assertTrue(t3["requires_human_approval"])

    def test_wallet_transfer_zero_and_negative_amounts(self):
        req_zero = WalletTransferRequest(
            source_wallet="Main Wallet",
            destination_wallet="Fun Wallet",
            amount=0.0,
        )
        res_zero = wallet_manager.execute_transfer(req_zero)
        self.assertFalse(res_zero.success)
        self.assertEqual(res_zero.status, "REJECTED")

        req_neg = WalletTransferRequest(
            source_wallet="Main Wallet",
            destination_wallet="Fun Wallet",
            amount=-100_000.0,
        )
        res_neg = wallet_manager.execute_transfer(req_neg)
        self.assertFalse(res_neg.success)
        self.assertEqual(res_neg.status, "REJECTED")

    def test_wallet_transfer_same_source_and_destination(self):
        req = WalletTransferRequest(
            source_wallet="Main Wallet",
            destination_wallet="Main Wallet",
            amount=500_000.0,
        )
        res = wallet_manager.execute_transfer(req)
        self.assertFalse(res.success)
        self.assertIn("different", res.message)

    def test_wallet_transfer_insufficient_funds(self):
        req = WalletTransferRequest(
            source_wallet="Fun Wallet",
            destination_wallet="Emergency Vault",
            amount=999_999_999.0,  # Far higher than Fun Wallet balance
        )
        res = wallet_manager.execute_transfer(req)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED")
        self.assertIn("Insufficient balance", res.message)

    def test_csv_parser_empty_and_corrupt_data(self):
        empty_csv = ""
        txs = DataIngestionEngine.parse_csv(empty_csv)
        self.assertEqual(len(txs), 0)

        corrupt_csv = "id,date,description,amount\nTX001,invalid-date,Coffee,-abc"
        txs_corrupt = DataIngestionEngine.parse_csv(corrupt_csv)
        self.assertEqual(len(txs_corrupt), 1)
        self.assertEqual(txs_corrupt[0].amount, 0.0)

    def test_monte_carlo_extreme_income_shock(self):
        # 100% chance of income disruption
        req = MonteCarloRequest(
            initial_savings=10_000_000.0,
            monthly_income=15_000_000.0,
            monthly_expenses=30_000_000.0,
            income_shock_prob=1.0,
            num_simulations=200,
        )
        res = MonteCarloEngine.simulate(req)
        self.assertGreater(res.bankruptcy_probability, 80.0)
        self.assertLess(res.resilience_score, 30.0)

    def test_anti_scam_extreme_ponzi_yield(self):
        # 10% daily yield
        req = AntiScamScanRequest(
            recipient_name="Crypto Matrix",
            recipient_account="000111222",
            bank_name="TestBank",
            amount=50_000_000.0,
            transfer_note="Cam ket lai 10% ngay x3 trong 1 tuan",
            advertised_yield_daily_pct=10.0,
        )
        res = AntiScamShield.scan_transfer_intent(req)
        self.assertTrue(res.is_locked)
        self.assertTrue(res.ponzi_math_flag)
        self.assertGreaterEqual(res.risk_score, 90.0)


if __name__ == "__main__":
    unittest.main()
