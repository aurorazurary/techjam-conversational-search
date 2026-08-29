from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent


PRODUCTS = [
    {
        "parent_asin": "SHOE_A",
        "title": "Supportive walking slipper",
        "features": ["Textile upper", "Rubber sole", "APMA accepted"],
        "description": ["Comfortable indoor walking shoe"],
        "price": 59.0,
        "categories": ["Women", "Shoes", "Slippers"],
        "details": {"Department": "womens"},
        "average_rating": 4.8,
        "rating_number": 120,
        "store": "Example Shoes",
    },
    {
        "parent_asin": "SHOE_B",
        "title": "Blue fashion sandal",
        "features": ["Synthetic upper", "Foam sole"],
        "description": ["A lightweight summer sandal"],
        "price": 29.0,
        "categories": ["Women", "Shoes", "Sandals"],
        "details": {"Department": "womens"},
        "average_rating": 4.2,
        "rating_number": 20,
        "store": "Example Sandals",
    },
    {
        "parent_asin": "SHOE_C",
        "title": "Leather hiking boot",
        "features": ["Leather upper", "Rubber sole"],
        "description": ["Durable outdoor hiking boot"],
        "price": 89.0,
        "categories": ["Women", "Shoes", "Boots"],
        "details": {"Department": "womens"},
        "average_rating": 4.5,
        "rating_number": 80,
        "store": "Example Boots",
    },
]


class AgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        catalog_path = Path(self.temporary_directory.name) / "catalog.jsonl"
        catalog_path.write_text(
            "".join(json.dumps(product) + "\n" for product in PRODUCTS),
            encoding="utf-8",
        )
        self.agent = Agent(catalog_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def reset(self, session_id: str = "session") -> None:
        self.agent.reset(
            session_id,
            {
                "preference_tags": ["comfort", "durability"],
                "average_prior_rating": 4.5,
                "rating_style": "usually positive",
                "purchase_frequency": "3-4 prior purchases",
                "summary": "Prior purchases emphasize comfort and durability.",
            },
        )

    def test_exact_constraints_are_reranked_and_remembered(self) -> None:
        self.reset()
        first = self.agent.respond(
            "session",
            "I'm looking for Shoes Slippers. A key requirement is: APMA accepted.",
            1,
            1,
        )
        self.assertEqual(first["recommendations"], [{"parent_asin": "SHOE_A"}])
        self.assertEqual(first["ask_attribute"], "other")

        second = self.agent.respond(
            "session",
            "Those options are not quite right yet. Ask me about one specific attribute.",
            2,
            1,
        )
        state = self.agent._sessions["session"]
        self.assertEqual(state.category, "Shoes Slippers")
        self.assertEqual(state.constraints, ["APMA accepted"])

    def test_boundary_answer_retries_a_broad_requirement_question(self) -> None:
        self.reset()
        first = self.agent.respond(
            "session", "I'm looking for Shoes Slippers, but I'm still exploring.", 1, 1
        )
        second = self.agent.respond(
            "session",
            "I don't have a preference for other; please use your judgment.",
            2,
            1,
        )
        self.assertEqual(first["ask_attribute"], "other")
        self.assertEqual(second["ask_attribute"], "other")

    def test_override_replaces_initial_preference_but_keeps_other_constraints(self) -> None:
        self.reset()
        first = self.agent.respond(
            "session", "I'm looking for Shoes Slippers. blue fashion", 1, 1
        )
        second = self.agent.respond(
            "session",
            "For that, what matters is: Textile upper; APMA accepted.",
            2,
            1,
        )
        third = self.agent.respond(
            "session",
            "Actually, ignore my earlier preference. What I need is: Rubber sole.",
            3,
            1,
        )
        state = self.agent._sessions["session"]
        self.assertNotIn("blue fashion", state.constraints)
        self.assertIn("Textile upper", state.constraints)
        self.assertIn("APMA accepted", state.constraints)
        self.assertIn("Rubber sole", state.constraints)
        self.assertNotEqual(first["recommendations"], third["recommendations"])
        self.assertEqual(second["recommendations"], third["recommendations"])

    def test_stable_search_does_not_repeat_failed_products(self) -> None:
        self.reset()
        first = self.agent.respond(
            "session", "I'm looking for Women Shoes, but I'm still exploring.", 1, 1
        )
        second = self.agent.respond(
            "session",
            "Those options are not quite right yet. Ask me about one specific attribute.",
            2,
            1,
        )
        self.assertNotEqual(first["recommendations"], second["recommendations"])

    def test_reset_is_required(self) -> None:
        with self.assertRaises(RuntimeError):
            self.agent.respond("missing", "I need shoes", 1, 10)


if __name__ == "__main__":
    unittest.main()
