import unittest

from app.operations.service import percentile95
from app.operations.rollout import is_user_in_rollout


class Phase10HardeningTests(unittest.TestCase):
    def test_percentile95_is_deterministic(self) -> None:
        self.assertIsNone(percentile95([]))
        self.assertEqual(percentile95([100]), 100)
        self.assertEqual(percentile95(list(range(1, 101))), 95)

    def test_rollout_percent_validation(self) -> None:
        from app.config import Settings
        with self.assertRaisesRegex(ValueError, "NOVA_ROLLOUT_PERCENT"):
            Settings(openai_api_key="x", jwt_secret="x", nova_rollout_percent=101)

    def test_rollout_cohort_is_stable_and_bounded(self) -> None:
        self.assertFalse(is_user_in_rollout(7, 0))
        self.assertTrue(is_user_in_rollout(7, 100))
        self.assertEqual(is_user_in_rollout(42, 25), is_user_in_rollout(42, 25))
