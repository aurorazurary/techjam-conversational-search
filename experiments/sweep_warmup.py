from __future__ import annotations

import sys

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from experiments.evaluate_split import stratified_split
from starter.agent import Agent

CATALOG = "data/catalog.jsonl"


def _line(name: str, r: dict) -> str:
    return (
        f"{name:>6}: TS={r['recommended_technical_score']:.6f} "
        f"HR={r['hit_rate_at_10']:.4f} MRR={r['mrr']:.6f} "
        f"MTTC={r['mttc']:.4f} EFF={r['efficiency']:.4f}"
    )


def run(configs: list[dict]) -> None:
    pub = load_jsonl("data/public_set.jsonl")
    dev, hold = stratified_split(pub, holdout_fraction=0.25)
    gen = load_jsonl("data/generalization_set.jsonl")
    gap = load_jsonl("data/category_gap_set.jsonl")
    catalog_ids, categories, products = catalog_index(CATALOG)
    parts = [("dev", dev), ("hold", hold), ("pub", pub), ("gen", gen), ("gap", gap)]
    for cfg in configs:
        agent = Agent(CATALOG, **cfg)
        print(cfg)
        for name, part in parts:
            r = evaluate(agent, part, catalog_ids, categories, products)
            print("  " + _line(name, r))
        sys.stdout.flush()


if __name__ == "__main__":
    run([
        {"warmup_k": 10, "warmup_max_evidence": -1.0},
        {"warmup_k": 2, "warmup_max_evidence": 2.0, "warmup_max_turn": 2},
        {"warmup_k": 2, "warmup_max_evidence": 2.0, "warmup_max_turn": 3},
        {"warmup_k": 2, "warmup_max_evidence": 2.0, "warmup_max_turn": 4},
        {"warmup_k": 3, "warmup_max_evidence": 2.0, "warmup_max_turn": 3},
    ])
