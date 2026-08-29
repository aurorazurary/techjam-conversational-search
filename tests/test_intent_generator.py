from __future__ import annotations

import sqlite3
import unittest

from starter.deepseek_client import DeepSeekJSONResponse
from starter.Intent_generator import IntentGenerator
from starter.Preference import PreferenceStore
from starter.Ranker import Ranker
from starter.intents import BuyingIntent, NoInfoIntent


class FakeDeepSeekClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    def complete_json(
        self, system_prompt: str, user_payload: dict
    ) -> DeepSeekJSONResponse:
        self.calls.append((system_prompt, user_payload))
        return DeepSeekJSONResponse(self.payload, 123, 45)


def intent_payload(**overrides: object) -> dict:
    payload: dict = {
        "scenario_signal": "info",
        "shopping_mode": "buying",
        "category_text": "",
        "constraints": [
            {
                "attribute": "feature",
                "value": "water resistant",
                "strength": "hard",
            }
        ],
        "replace_attribute": None,
        "no_preference_attr": None,
        "confidence": 0.95,
    }
    payload.update(overrides)
    return payload


class IntentGeneratorTest(unittest.TestCase):
    def test_hybrid_keeps_high_confidence_rules_offline(self) -> None:
        client = FakeDeepSeekClient(intent_payload())
        generator = IntentGenerator(client, mode="hybrid")

        intent = generator.generate(
            "I'm looking for boots. A key requirement is: waterproof.", 1, {}
        )

        self.assertIsInstance(intent, BuyingIntent)
        self.assertEqual(client.calls, [])
        self.assertEqual(intent.prompt_tokens, 0)

    def test_hybrid_parses_ambiguous_message_with_state_context(self) -> None:
        client = FakeDeepSeekClient(intent_payload())
        generator = IntentGenerator(client, mode="hybrid")
        context = {"category": "boots", "last_asked_attribute": "feature"}

        intent = generator.generate("Make them okay for heavy rain", 2, context)

        self.assertEqual(intent.scenario_signal, "info")
        self.assertEqual(intent.shopping_mode, "buying")
        self.assertEqual(intent.constraints[0]["attribute"], "feature")
        self.assertEqual(intent.constraints[0]["hardness"], 1.0)
        self.assertEqual(intent.prompt_tokens, 123)
        self.assertEqual(intent.completion_tokens, 45)
        self.assertEqual(client.calls[0][1]["current_state"], context)

    def test_invalid_model_payload_falls_back_to_no_info(self) -> None:
        client = FakeDeepSeekClient(intent_payload(confidence=0.1))
        generator = IntentGenerator(client, mode="always")

        intent = generator.generate("ambiguous", 2, {})

        self.assertIsInstance(intent, NoInfoIntent)
        self.assertEqual(intent.prompt_tokens, 0)

    def test_structured_override_replaces_only_one_attribute(self) -> None:
        client = FakeDeepSeekClient(
            intent_payload(
                scenario_signal="override",
                constraints=[
                    {"attribute": "color", "value": "black", "strength": "hard"}
                ],
                replace_attribute="color",
            )
        )
        intent = IntentGenerator(client, mode="always").generate(
            "Forget red; black would be better", 3, {}
        )
        store = PreferenceStore(profile_tags=[])
        store.initial_preference = "red"
        store.add_preference("color", "red")
        store.add_preference("feature", "waterproof")

        Ranker(sqlite3.connect(":memory:")).apply_intent(store, intent)

        self.assertEqual(store.initial_preference, "")
        self.assertEqual(
            [(preference.attribute, preference.value) for preference in store.preferences],
            [("feature", "waterproof"), ("color", "black")],
        )


if __name__ == "__main__":
    unittest.main()
