from __future__ import annotations

import argparse
import json

from starter.Intent_generator import IntentGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one environment-configured DeepSeek intent parse."
    )
    parser.add_argument(
        "--message",
        default="Forget red; I would rather have a waterproof black jacket.",
    )
    parser.add_argument("--turn", type=int, default=3)
    args = parser.parse_args()

    generator = IntentGenerator.from_env()
    if generator.client is None or generator.mode == "off":
        raise SystemExit(
            "DeepSeek is disabled; export DEEPSEEK_API_KEY and set "
            "DEEPSEEK_MODE=always or hybrid."
        )
    intent = generator.generate(
        args.message,
        args.turn,
        {
            "shopping_mode": "buying",
            "category": "jackets",
            "preferences": [
                {"attribute": "color", "value": "red", "strength": "soft"}
            ],
            "last_asked_attribute": "feature",
            "declined_attributes": [],
        },
    )
    print(
        json.dumps(
            {
                "scenario_signal": intent.scenario_signal,
                "shopping_mode": intent.shopping_mode,
                "category_text": intent.category_text,
                "constraints": intent.constraints,
                "replace_attribute": intent.replace_attribute,
                "no_preference_attr": intent.no_preference_attr,
                "confidence": intent.confidence,
                "usage": {
                    "prompt_tokens": intent.prompt_tokens,
                    "completion_tokens": intent.completion_tokens,
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
