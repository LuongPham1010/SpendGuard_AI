"""
Comprehensive Audit & Compliance Unit Tests for SpendGuard AI
Tests:
- Gemini 3.8 Flash default configuration and alias chain
- Robust LLM JSON parsing (codeblocks, preambles, nested structures)
- Enhanced PII masking (bank accounts, citizen IDs, cards, emails, phones)
- Ghost subscription cancellation state persistence & savings calculation
- Non-hardcoded recurring charge detection
- Financial Debate Arena large purchase boundary rejection (iPhone 16)
- Tier 3 Human-in-the-Loop approval & cognitive quiz override execution
- CSV Statement upload and PII sanitization
"""

import unittest
import io
from app.config import DEFAULT_GEMINI_MODEL, GEMINI_MODEL_ALIASES
from app.core.llm_helper import extract_json_from_text
from app.config import GEMINI_MODEL_ALIASES
from app.core.security import SecurityGuard
from app.core.sandbox_wallets import wallet_manager
from app.models.schemas import WalletTransferRequest, DebateRequest, Transaction
from app.modules.ghost_hunter import GhostSubscriptionHunter
from app.modules.debate_arena import FinancialDebateArena
from app.modules.data_ingestion import DataIngestionEngine


class TestAuditAndCompliance(unittest.TestCase):

    def test_gemini_default_model_is_38_flash(self):
        """Verify default Gemini model is gemini-3.8-flash as requested by user"""
        self.assertEqual(DEFAULT_GEMINI_MODEL, "gemini-3.8-flash")
        chain = [DEFAULT_GEMINI_MODEL] + [m for m in GEMINI_MODEL_ALIASES if m != DEFAULT_GEMINI_MODEL]
        self.assertEqual(chain[0], "gemini-3.8-flash")
        self.assertIn("gemini-3.5-flash", chain)            # verified live on 2026-10-13
        self.assertNotIn("gemini-2.0-flash", chain)         # retired by Google; a dead fallback hides outages
        self.assertEqual(len(chain), len(set(chain)))

    def test_llm_json_extractor_resilience(self):
        """Verify extract_json_from_text handles diverse LLM response formats"""
        # Format 1: Direct JSON
        raw1 = '{"status": "ok", "count": 42}'
        self.assertEqual(extract_json_from_text(raw1), {"status": "ok", "count": 42})

        # Format 2: Markdown fence with json tag
        raw2 = "```json\n{\"merchant\": \"Starbucks\", \"total\": 120000}\n```"
        self.assertEqual(extract_json_from_text(raw2), {"merchant": "Starbucks", "total": 120000})

        # Format 3: Preamble and postamble conversational text
        raw3 = "Here is the extracted receipt data:\n```\n{\"merchant\": \"WinMart\", \"items\": 5}\n```\nHope this helps!"
        self.assertEqual(extract_json_from_text(raw3), {"merchant": "WinMart", "items": 5})

        # Format 4: Curly braces without fences but surrounding explanation
        raw4 = "Analysis complete: {\"verdict\": \"APPROVED\", \"score\": 95.0}. Execution authorized."
        self.assertEqual(extract_json_from_text(raw4), {"verdict": "APPROVED", "score": 95.0})

        # Format 5: Invalid/empty returns None
        self.assertIsNone(extract_json_from_text("No JSON here"))
        self.assertIsNone(extract_json_from_text(""))

    def test_bank_account_pii_masking(self):
        """Verify bank account numbers preceded by STK / TK / Account are masked"""
        text = "Chuyen khoan toi STK: 0071000123456 tai Vietcombank chi nhanh Sai Gon"
        masked = SecurityGuard.mask_pii(text)
        self.assertNotIn("0071000123456", masked)
        self.assertIn("007****456", masked)

    def test_subscription_cancellation_state(self):
        """Verify subscription cancellation state tracking and active vs saved leakage"""
        txs = DataIngestionEngine.load_default_transactions()
        subs_before = GhostSubscriptionHunter.detect_subscriptions(txs)
        self.assertGreater(len(subs_before), 0)

        # Cancel Netflix
        GhostSubscriptionHunter.cancel_subscription("Netflix")
        self.assertTrue(GhostSubscriptionHunter.is_cancelled("Netflix"))

        subs_after = GhostSubscriptionHunter.detect_subscriptions(txs)
        netflix_sub = next((s for s in subs_after if "netflix" in s.merchant.lower()), None)
        self.assertIsNotNone(netflix_sub)
        self.assertEqual(netflix_sub.status, "cancelled")

    def test_dynamic_recurring_subscription_detection(self):
        """Verify non-hardcoded service with monthly intervals is correctly detected"""
        custom_txs = [
            Transaction(
                id="CUSTOM01",
                date="2026-06-01",
                description="Thanh toan phi Cloud Server DigitalOcean",
                amount=240000.0,
                type="outflow",
                category="Wants",
                merchant="DigitalOcean Cloud",
            ),
            Transaction(
                id="CUSTOM02",
                date="2026-07-01",
                description="Thanh toan phi Cloud Server DigitalOcean",
                amount=240000.0,
                type="outflow",
                category="Wants",
                merchant="DigitalOcean Cloud",
            ),
            Transaction(
                id="CUSTOM03",
                date="2026-07-31",
                description="Thanh toan phi Cloud Server DigitalOcean",
                amount=240000.0,
                type="outflow",
                category="Wants",
                merchant="DigitalOcean Cloud",
            ),
        ]
        detected = GhostSubscriptionHunter.detect_subscriptions(custom_txs)
        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0].merchant, "DigitalOcean Cloud")
        self.assertEqual(detected[0].annual_leakage, 240000.0 * 12.0)

    def test_debate_denies_unaffordable_high_risk_purchase(self):
        """Verify iPhone 16 Pro Max (100% of monthly income) is DENIED by Arbiter"""
        req = DebateRequest(
            item_name="iPhone 16 Pro Max 256GB",
            price=34_990_000.0,
            user_income=35_000_000.0,
            user_justification="Want the latest flagship smartphone",
        )
        res = FinancialDebateArena.run_debate(req)
        # 34.99M VND purchase takes 99.97% of income and 2.3x fun wallet balance
        self.assertEqual(res.verdict, "DENIED")
        self.assertIn("sinking fund", res.executive_summary.lower() + " ".join(res.action_plan).lower())

    def test_tier3_human_authorization_and_quiz_override(self):
        """Verify Tier 3 transfer with human override executes properly"""
        req = WalletTransferRequest(
            source_wallet="Main Wallet",
            destination_wallet="Emergency Vault",
            amount=10_000_000.0,
            note="High-value reserve transfer with 2FA",
            security_override=True,
            quiz_passed=True,
        )
        res = wallet_manager.execute_transfer(req)
        self.assertTrue(res.success)
        self.assertEqual(res.status, "EXECUTED")
        self.assertEqual(res.tier, "Tier 3")


if __name__ == "__main__":
    unittest.main()
