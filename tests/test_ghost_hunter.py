"""
Unit Tests for Ghost Subscription Hunter
"""

import unittest
from app.modules.data_ingestion import DataIngestionEngine
from app.modules.ghost_hunter import GhostSubscriptionHunter


class TestGhostHunter(unittest.TestCase):

    def setUp(self):
        self.txs = DataIngestionEngine.load_default_transactions()

    def test_detect_subscriptions(self):
        subs = GhostSubscriptionHunter.detect_subscriptions(self.txs)
        self.assertGreater(len(subs), 0, "Should detect at least 1 recurring subscription")

        merchant_names = [s.merchant.lower() for s in subs]
        
        # Verify key recurring merchants
        self.assertTrue(any("netflix" in m for m in merchant_names), "Should detect Netflix subscription")
        self.assertTrue(any("spotify" in m for m in merchant_names), "Should detect Spotify subscription")
        self.assertTrue(any("icloud" in m or "apple" in m for m in merchant_names), "Should detect iCloud subscription")

    def test_annual_leakage_calculation(self):
        subs = GhostSubscriptionHunter.detect_subscriptions(self.txs)
        for sub in subs:
            self.assertEqual(
                round(sub.annual_leakage, 2),
                round(sub.amount * 12.0, 2),
                f"Annual leakage for {sub.merchant} should be 12x monthly amount"
            )

    def test_cancellation_templates(self):
        subs = GhostSubscriptionHunter.detect_subscriptions(self.txs)
        netflix_sub = next((s for s in subs if "netflix" in s.merchant.lower()), None)
        self.assertIsNotNone(netflix_sub)
        
        # Verify EN template
        self.assertIn("Immediate Cancellation Request", netflix_sub.email_template_en)
        self.assertIn("Netflix", netflix_sub.email_template_en)
        
        # Verify VI template
        self.assertIn("Yêu cầu Hủy gói Đăng ký Dịch vụ", netflix_sub.email_template_vi)
        self.assertIn("Netflix", netflix_sub.email_template_vi)

    def test_recurrence_delta_window(self):
        subs = GhostSubscriptionHunter.detect_subscriptions(self.txs)
        for sub in subs:
            # Average frequency should be approximately 30-31 days
            self.assertGreaterEqual(sub.frequency_days, 25.0)
            self.assertLessEqual(sub.frequency_days, 35.0)


if __name__ == "__main__":
    unittest.main()
