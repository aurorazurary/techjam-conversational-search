from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from experiments.evaluate_split import SPLIT_SALT, stratified_split
from starter.agent import Agent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep title-diversity strengths on development with shared caches."
    )
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--strengths", default="5,6,8")
    parser.add_argument("--output", help="Optional JSON result path")
    args = parser.parse_args()

    strengths = [float(value) for value in args.strengths.split(",") if value.strip()]
    if not strengths:
        raise ValueError("at least one diversity strength is required")

    development, _ = stratified_split(load_jsonl(args.dataset))
    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog)
    results: dict[str, dict] = {}
    for strength in strengths:
        agent.diversity_strength = max(0.0, strength)
        results[str(strength)] = evaluate(
            agent, development, catalog_ids, categories, products
        )

    payload = {
        "split_salt": SPLIT_SALT,
        "partition": "development",
        "strengths": strengths,
        "results": results,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                **payload,
                "results": {
                    strength: {
                        key: value
                        for key, value in result.items()
                        if key != "sessions"
                    }
                    for strength, result in results.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
