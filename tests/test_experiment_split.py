from __future__ import annotations

import unittest
from collections import Counter

from experiments.evaluate_split import stratified_split


class ExperimentSplitTest(unittest.TestCase):
    def test_split_is_deterministic_disjoint_and_stratified(self) -> None:
        samples = [
            {"sample_id": f"{scenario}_{index:03d}", "scenario_type": scenario}
            for scenario, count in (
                ("buying", 80),
                ("browsing", 80),
                ("intent_override", 30),
                ("boundary", 10),
            )
            for index in range(count)
        ]
        development, holdout = stratified_split(samples)
        development_again, holdout_again = stratified_split(list(reversed(samples)))

        development_ids = {sample["sample_id"] for sample in development}
        holdout_ids = {sample["sample_id"] for sample in holdout}
        self.assertEqual(len(development), 150)
        self.assertEqual(len(holdout), 50)
        self.assertFalse(development_ids & holdout_ids)
        self.assertEqual(development_ids | holdout_ids, {sample["sample_id"] for sample in samples})
        self.assertEqual(development_ids, {sample["sample_id"] for sample in development_again})
        self.assertEqual(holdout_ids, {sample["sample_id"] for sample in holdout_again})
        self.assertEqual(
            Counter(sample["scenario_type"] for sample in holdout),
            Counter({"buying": 20, "browsing": 20, "intent_override": 8, "boundary": 2}),
        )

    def test_invalid_fraction_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            stratified_split([], holdout_fraction=1.0)


if __name__ == "__main__":
    unittest.main()
