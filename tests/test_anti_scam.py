"""
Unit Tests for Cognitive Anti-Scam Shield & 3-Tier Security Matrix
"""

import unittest
from app.modules.anti_scam_shield import AntiScamShield
from app.models.schemas import AntiScamScanRequest, WalletTransferRequest
from app.core.security import SecurityGuard
from app.core.sandbox_wallets import wallet_manager


class TestAntiScamAndSecurity(unittest.TestCase):

    def test_benign_transfer_scan(self):
        req = AntiScamScanRequest(
            recipient_name="Nguyen Van A",
            recipient_account="1029384756",
            bank_name="Vietcombank",
            amount=500_000.0,
            transfer_note="Tien an trua sinh nhat",
            advertised_yield_daily_pct=0.0,
            source_context="Ban than chuyen tien an uong",
        )
        res = AntiScamShield.scan_transfer_intent(req)
        self.assertFalse(res.is_locked)
        self.assertLess(res.risk_score, 50.0)
        self.assertEqual(len(res.cognitive_quiz), 0)

    def test_ponzi_and_urgency_lockdown(self):
        req = AntiScamScanRequest(
            recipient_name="VIP Investment Bot",
            recipient_account="999888777666",
            bank_name="Digital Bank",
            amount=25_000_000.0,
            transfer_note="Chuyen tien gap trong 15 phut de vao phong VIP nhan lai 2.5% ngay",
            advertised_yield_daily_pct=2.5,
            source_context="Tham gia nhom Telegram VIP duoc admin cam ket lai khung",
        )
        res = AntiScamShield.scan_transfer_intent(req)
        self.assertTrue(res.is_locked, "Should enforce Tier 3 lockdown on high risk")
        self.assertGreaterEqual(res.risk_score, 80.0)
        self.assertTrue(res.urgency_detected)
        self.assertTrue(res.ponzi_math_flag)
        self.assertEqual(res.cooling_off_minutes, 60)
        self.assertEqual(len(res.cognitive_quiz), 3)

    def test_tier_matrix_evaluation(self):
        # Tier 1: Read only
        t1 = SecurityGuard.evaluate_tier("READ_ONLY", amount=0)
        self.assertEqual(t1["tier"], "Tier 1")
        self.assertFalse(t1["requires_human_approval"])

        # Tier 2: Internal transfer <= 5M VND
        t2 = SecurityGuard.evaluate_tier("INTERNAL_TRANSFER", amount=3_000_000.0)
        self.assertEqual(t2["tier"], "Tier 2")
        self.assertFalse(t2["requires_human_approval"])

        # Tier 3: Internal transfer > 5M VND without override
        t3 = SecurityGuard.evaluate_tier("INTERNAL_TRANSFER", amount=10_000_000.0, is_override=False)
        self.assertEqual(t3["tier"], "Tier 3")
        self.assertTrue(t3["requires_human_approval"])

        # Tier 3 with human override
        t3_ovr = SecurityGuard.evaluate_tier("INTERNAL_TRANSFER", amount=10_000_000.0, is_override=True)
        self.assertEqual(t3_ovr["tier"], "Tier 3")
        self.assertEqual(t3_ovr["status"], "APPROVED")

    def test_wallet_manager_transfer_flow(self):
        # Small transfer: Tier 2 auto executes
        req = WalletTransferRequest(
            source_wallet="Main Wallet",
            destination_wallet="Fun Wallet",
            amount=100_000.0,
            note="Test small transfer",
        )
        res = wallet_manager.execute_transfer(req)
        self.assertTrue(res.success)
        self.assertEqual(res.status, "EXECUTED")
        self.assertEqual(res.tier, "Tier 2")


if __name__ == "__main__":
    unittest.main()
