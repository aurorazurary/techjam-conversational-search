from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_SEED = "techjam-generalization-v1"
SCENARIO_SPECS = {
    "buying": (40, "easy"),
    "browsing": (40, "medium"),
    "intent_override": (15, "hard"),
    "boundary": (5, "medium"),
}
EXPECTED_FIELDS = {
    "category_bucket",
    "difficulty_bucket",
    "ground_truth",
    "sample_id",
    "scenario_type",
    "user_profile",
}


def load_jsonl(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _stable_key(seed: str, namespace: str, value: str) -> str:
    material = f"{seed}\0{namespace}\0{value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _valid_catalog_product(product: dict) -> bool:
    parent_asin = str(product.get("parent_asin") or "").strip()
    title = str(product.get("title") or "").strip()
    categories = product.get("categories")
    return bool(parent_asin and title and isinstance(categories, list) and categories)


def build_generalization_samples(
    catalog_products: list[dict],
    public_samples: list[dict],
    *,
    seed: str = DEFAULT_SEED,
) -> list[dict]:
    """Build 100 public-schema sessions using catalog targets absent from public data."""
    public_targets = {
        str(sample.get("ground_truth", {}).get("parent_asin") or "").strip()
        for sample in public_samples
    }
    targets_by_id = {
        str(product["parent_asin"]).strip(): product
        for product in catalog_products
        if _valid_catalog_product(product)
        and str(product["parent_asin"]).strip() not in public_targets
    }
    ordered_targets = sorted(
        targets_by_id,
        key=lambda target: _stable_key(seed, "target", target),
    )
    required_count = sum(count for count, _ in SCENARIO_SPECS.values())
    if len(ordered_targets) < required_count:
        raise ValueError("catalog does not contain enough eligible non-public targets")

    profiles_by_scenario: dict[str, list[dict]] = defaultdict(list)
    for sample in public_samples:
        scenario = str(sample.get("scenario_type") or "")
        if scenario in SCENARIO_SPECS and isinstance(sample.get("user_profile"), dict):
            profiles_by_scenario[scenario].append(sample)

    slots: list[tuple[str, int, dict]] = []
    for scenario, (count, _) in SCENARIO_SPECS.items():
        source_samples = sorted(
            profiles_by_scenario[scenario],
            key=lambda sample: _stable_key(
                seed, "profile", str(sample.get("sample_id") or "")
            ),
        )
        if len(source_samples) < count:
            raise ValueError(f"public data does not contain {count} {scenario} profiles")
        for scenario_index, source in enumerate(source_samples[:count], start=1):
            slots.append((scenario, scenario_index, source))

    slots.sort(
        key=lambda slot: _stable_key(seed, "scenario", f"{slot[0]}:{slot[1]}")
    )
    samples: list[dict] = []
    for sample_index, (target, slot) in enumerate(
        zip(ordered_targets[:required_count], slots), start=1
    ):
        scenario, _, source = slot
        _, difficulty = SCENARIO_SPECS[scenario]
        samples.append(
            {
                "category_bucket": "clothing",
                "difficulty_bucket": difficulty,
                "ground_truth": {"parent_asin": target},
                "sample_id": f"generalization_{sample_index:03d}",
                "scenario_type": scenario,
                "user_profile": copy.deepcopy(source["user_profile"]),
            }
        )

    validate_generalization_samples(
        samples,
        public_targets=public_targets,
        catalog_ids=set(targets_by_id),
    )
    return samples


def validate_generalization_samples(
    samples: list[dict],
    *,
    public_targets: set[str] | None = None,
    catalog_ids: set[str] | None = None,
) -> None:
    expected_count = sum(count for count, _ in SCENARIO_SPECS.values())
    if len(samples) != expected_count:
        raise ValueError(f"expected {expected_count} samples, received {len(samples)}")

    sample_ids = [str(sample.get("sample_id") or "") for sample in samples]
    targets = [
        str(sample.get("ground_truth", {}).get("parent_asin") or "").strip()
        for sample in samples
    ]
    if len(set(sample_ids)) != expected_count or any(not value for value in sample_ids):
        raise ValueError("sample IDs must be non-empty and unique")
    if len(set(targets)) != expected_count or any(not value for value in targets):
        raise ValueError("target IDs must be non-empty and unique")

    scenario_counts = Counter(str(sample.get("scenario_type") or "") for sample in samples)
    expected_scenarios = Counter(
        {scenario: count for scenario, (count, _) in SCENARIO_SPECS.items()}
    )
    if scenario_counts != expected_scenarios:
        raise ValueError(f"invalid scenario mix: {dict(scenario_counts)}")

    for sample in samples:
        if set(sample) != EXPECTED_FIELDS:
            raise ValueError(f"invalid public schema for {sample.get('sample_id')}")
        scenario = str(sample["scenario_type"])
        expected_difficulty = SCENARIO_SPECS[scenario][1]
        if sample["difficulty_bucket"] != expected_difficulty:
            raise ValueError(f"invalid difficulty for {sample['sample_id']}")
        if sample["category_bucket"] != "clothing":
            raise ValueError(f"invalid category bucket for {sample['sample_id']}")
        if not isinstance(sample["user_profile"], dict):
            raise ValueError(f"invalid user profile for {sample['sample_id']}")
        if "intent_card" in sample or "behavior" in sample:
            raise ValueError("participant fixture must not expose hidden simulator fields")

    if public_targets and set(targets) & public_targets:
        raise ValueError("generalization targets must not overlap public targets")
    if catalog_ids is not None and not set(targets) <= catalog_ids:
        raise ValueError("generalization target is missing from the frozen catalog")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic 100-session public-schema audit set"
    )
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--public-set", default="data/public_set.jsonl")
    parser.add_argument("--output", default="data/generalization_set.jsonl")
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args()

    catalog_products = load_jsonl(args.catalog)
    public_samples = load_jsonl(args.public_set)
    samples = build_generalization_samples(
        catalog_products,
        public_samples,
        seed=args.seed,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(sample, sort_keys=True) + "\n" for sample in samples),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "sample_count": len(samples),
                "scenario_counts": dict(
                    sorted(Counter(sample["scenario_type"] for sample in samples).items())
                ),
                "seed": args.seed,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
