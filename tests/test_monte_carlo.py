"""
Unit Tests for Quantitative Monte Carlo Engine
"""

import unittest
from app.modules.monte_carlo import MonteCarloEngine
from app.models.schemas import MonteCarloRequest


class TestMonteCarlo(unittest.TestCase):

    def test_simulation_percentiles_order(self):
        req = MonteCarloRequest(
            initial_savings=50_000_000.0,
            monthly_income=35_000_000.0,
            monthly_expenses=22_000_000.0,
            num_simulations=1000,
            months=12,
            income_shock_prob=0.10,
            emergency_shock_min=5_000_000.0,
            emergency_shock_max=20_000_000.0,
            inflation_rate=0.10,
        )

        res = MonteCarloEngine.simulate(req)

        # Check lengths
        self.assertEqual(len(res.months), 13)
        self.assertEqual(len(res.percentile_10), 13)
        self.assertEqual(len(res.percentile_50), 13)
        self.assertEqual(len(res.percentile_90), 13)

        # Check percentile ordering: P10 <= P50 <= P90
        for i in range(13):
            self.assertLessEqual(
                res.percentile_10[i],
                res.percentile_50[i],
                f"Month {i}: P10 should be <= P50"
            )
            self.assertLessEqual(
                res.percentile_50[i],
                res.percentile_90[i],
                f"Month {i}: P50 should be <= P90"
            )

    def test_resilience_score_bounds(self):
        req = MonteCarloRequest(
            initial_savings=100_000_000.0,
            monthly_income=40_000_000.0,
            monthly_expenses=20_000_000.0,
            num_simulations=500,
        )
        res = MonteCarloEngine.simulate(req)
        self.assertGreaterEqual(res.resilience_score, 0.0)
        self.assertLessEqual(res.resilience_score, 100.0)
        self.assertGreaterEqual(res.bankruptcy_probability, 0.0)
        self.assertLessEqual(res.bankruptcy_probability, 100.0)

    def test_recommended_buffer(self):
        expenses = 25_000_000.0
        req = MonteCarloRequest(monthly_expenses=expenses)
        res = MonteCarloEngine.simulate(req)
        expected_buffer = expenses * 6.0
        self.assertEqual(res.recommended_emergency_buffer, expected_buffer)


if __name__ == "__main__":
    unittest.main()
