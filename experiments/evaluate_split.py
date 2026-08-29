from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from starter.agent import Agent


SPLIT_SALT = "techjam-public-split-v1"


def _split_key(sample: dict) -> bytes:
    sample_id = str(sample["sample_id"])
    return hashlib.sha256(f"{SPLIT_SALT}:{sample_id}".encode()).digest()


def stratified_split(
    samples: list[dict], holdout_fraction: float = 0.25
) -> tuple[list[dict], list[dict]]:
    if not 0.0 < holdout_fraction < 1.0:
        raise ValueError("holdout_fraction must be between zero and one")
    groups: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        groups[str(sample["scenario_type"])].append(sample)

    holdout_ids: set[str] = set()
    for group in groups.values():
        ordered = sorted(group, key=_split_key)
        holdout_count = max(1, round(len(ordered) * holdout_fraction))
        holdout_ids.update(str(sample["sample_id"]) for sample in ordered[:holdout_count])

    development = [
        sample for sample in samples if str(sample["sample_id"]) not in holdout_ids
    ]
    holdout = [sample for sample in samples if str(sample["sample_id"]) in holdout_ids]
    return development, holdout


def _summary(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "sessions"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the agent on deterministic public development/holdout splits."
    )
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument(
        "--split", choices=("development", "holdout", "both", "all"), default="both"
    )
    parser.add_argument("--output", help="Optional JSON path for detailed split results")
    parser.add_argument(
        "--weights",
        help="Optional JSON object or JSON file containing reranker weight overrides",
    )
    parser.add_argument("--diversity-strength", type=float, default=6.0)
    parser.add_argument("--broad-question-limit", type=int, default=2)
    parser.add_argument("--expand-query-terms", action="store_true")
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    development, holdout = stratified_split(samples)
    partitions = {
        "development": development,
        "holdout": holdout,
        "all": samples,
    }
    selected = ("development", "holdout") if args.split == "both" else (args.split,)

    weight_overrides = None
    if args.weights:
        weights_text = (
            args.weights
            if args.weights.lstrip().startswith("{")
            else Path(args.weights).read_text(encoding="utf-8")
        )
        weight_overrides = {
            str(key): float(value) for key, value in json.loads(weights_text).items()
        }

    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(
        args.catalog,
        rerank_weights=weight_overrides,
        diversity_strength=args.diversity_strength,
        broad_question_limit=args.broad_question_limit,
        expand_query_terms=args.expand_query_terms,
    )
    results = {
        name: evaluate(agent, partitions[name], catalog_ids, categories, products)
        for name in selected
    }
    payload = {
        "split_salt": SPLIT_SALT,
        "partition_sizes": {
            "development": len(development),
            "holdout": len(holdout),
            "all": len(samples),
        },
        "experiment": {
            "weight_overrides": weight_overrides or {},
            "diversity_strength": args.diversity_strength,
            "broad_question_limit": args.broad_question_limit,
            "expand_query_terms": args.expand_query_terms,
        },
        "results": results,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "results": {k: _summary(v) for k, v in results.items()}}, indent=2))


if __name__ == "__main__":
    main()
