# Competition Data

## `public_set.jsonl`

Contains 200 labeled development sessions: 80 Buying, 80 Browsing, 30 Intent Override, and 10 Boundary sessions.

Each session contains a safe aggregate `user_profile` and public labels for local development. Direct user identifiers, timestamps, free-text reviews, raw purchase history, hidden intent cards, and simulator-policy internals are not shipped in this participant file.

## `generalization_set.jsonl`

Contains 100 deterministic local audit sessions with the same participant-visible
schema, scenario-to-difficulty mapping, and 40% Buying / 40% Browsing / 15% Intent
Override / 5% Boundary mix as the organizer's public set. Its target products are
catalog-valid, unique, and disjoint from all 200 public targets. Safe aggregate
profiles are sampled within the matching public scenario class.

The file is a participant-created robustness fixture, not organizer data or an
independent private-set estimate. It intentionally omits `intent_card` and `behavior`;
the unchanged evaluator derives both from frozen catalog metadata exactly as it does
for `public_set.jsonl`.

- Deterministic seed: `techjam-generalization-v1`
- SHA-256: `5b0a4c0b639a1c813b7ac7674a6f180cb0f19c30ef693d691eab84af0923e1e8`

Regenerate and evaluate it with:

```bash
python3 -m experiments.generate_generalization_set
python3 -m evaluator.local_evaluator \
  --dataset data/generalization_set.jsonl \
  --output /tmp/techjam_generalization_results.json
```

## `generalization_set_v2.jsonl`

A second, independently-seeded audit fixture built with the same script and schema
as `generalization_set.jsonl` above, to check whether that seed's -0.023
TechnicalScore gap (vs. the public 200) was a systemic weakness or ordinary
seed-to-seed variance. Result: this seed scores 0.874588 (-0.004 vs public), and
its one miss is a different scenario (1 Intent Override) than the first seed's
three Browsing misses -- consistent with variance, not a single systemic gap.

- Deterministic seed: `techjam-generalization-v2`
- SHA-256: `0140cde20ee3c86945439690d0b1534181037da549dcfc5c140db4b5ef54d8d3`

Regenerate and evaluate it with:

```bash
python3 -m experiments.generate_generalization_set \
  --seed techjam-generalization-v2 --output data/generalization_set_v2.jsonl
python3 -m evaluator.local_evaluator \
  --dataset data/generalization_set_v2.jsonl \
  --output /tmp/techjam_generalization_v2_results.json
```

## `catalog.jsonl`

Download `catalog.jsonl.gz` from the GitHub Release and decompress it as `catalog.jsonl` in this directory. Expected row count: 50,000.

Never place API keys, private evaluation data, or participant outputs in this directory.
