from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from experiments.generate_generalization_set import (
    EXPECTED_FIELDS,
    SCENARIO_SPECS,
    build_generalization_samples,
    validate_generalization_samples,
)


ROOT = Path(__file__).resolve().parents[1]
FROZEN_SHA256 = "5b0a4c0b639a1c813b7ac7674a6f180cb0f19c30ef693d691eab84af0923e1e8"


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class GeneralizationSetTest(unittest.TestCase):
    def test_frozen_set_matches_public_contract(self) -> None:
        public_samples = _load_jsonl(ROOT / "data" / "public_set.jsonl")
        audit_path = ROOT / "data" / "generalization_set.jsonl"
        audit_samples = _load_jsonl(audit_path)
        public_targets = {
            sample["ground_truth"]["parent_asin"] for sample in public_samples
        }

        self.assertEqual(hashlib.sha256(audit_path.read_bytes()).hexdigest(), FROZEN_SHA256)
        validate_generalization_samples(
            audit_samples,
            public_targets=public_targets,
        )
        self.assertTrue(all(set(sample) == EXPECTED_FIELDS for sample in audit_samples))
        self.assertEqual(
            Counter(sample["scenario_type"] for sample in audit_samples),
            Counter(
                {scenario: count for scenario, (count, _) in SCENARIO_SPECS.items()}
            ),
        )
        self.assertTrue(
            all("intent_card" not in sample and "behavior" not in sample for sample in audit_samples)
        )

    def test_generator_is_deterministic_and_excludes_public_targets(self) -> None:
        scenarios = [
            scenario
            for scenario, (count, _) in SCENARIO_SPECS.items()
            for _ in range(count * 2)
        ]
        public_samples = [
            {
                "sample_id": f"public_{index:03d}",
                "scenario_type": scenario,
                "ground_truth": {"parent_asin": f"PUBLIC{index:04d}"},
                "user_profile": {
                    "average_prior_rating": 5.0,
                    "preference_tags": ["material", "fit"],
                    "purchase_frequency": "3-4 prior purchases",
                    "rating_style": "usually positive",
                    "summary": "Synthetic safe aggregate profile.",
                },
            }
            for index, scenario in enumerate(scenarios, start=1)
        ]
        catalog_products = [
            {
                "parent_asin": sample["ground_truth"]["parent_asin"],
                "title": "Public product",
                "categories": ["Clothing"],
            }
            for sample in public_samples
        ] + [
            {
                "parent_asin": f"NEW{index:04d}",
                "title": f"New product {index}",
                "categories": ["Clothing", "Test category"],
            }
            for index in range(130)
        ]

        first = build_generalization_samples(catalog_products, public_samples)
        second = build_generalization_samples(catalog_products, public_samples)

        self.assertEqual(first, second)
        public_targets = {
            sample["ground_truth"]["parent_asin"] for sample in public_samples
        }
        generated_targets = {
            sample["ground_truth"]["parent_asin"] for sample in first
        }
        self.assertFalse(public_targets & generated_targets)


if __name__ == "__main__":
    unittest.main()
