# Offline Conversational Search Agent

## Summary

The submitted agent is a stateful, fully offline shopping search system. It combines
SQLite FTS5 candidate retrieval with structured constraint reranking and an adaptive
clarification policy. It does not require an LLM, API key, network access, model
download, or third-party Python dependency.

## Architecture

### Catalog index

At startup, the agent builds an in-memory FTS5 index over title, category, features,
details, store, and description. Numeric price, rating, and rating-count fields are
stored alongside the searchable text for reranking.

### Conversation state

For every session, the agent retains:

- the coarse product category;
- disclosed hard and soft constraints;
- aggregate profile preference tags;
- attributes already asked or declined;
- products already recommended; and
- the initial preference that may later be replaced.

Generic evaluator feedback is excluded from the search query. When an intent override
occurs, the superseded initial preference is removed, compatible constraints remain,
and previously shown products become eligible again because an early target cannot be
scored before the override turn.

### Clarification policy

The agent recommends products and asks a question on the same turn. It starts with a
broad must-have question represented by the allowed `other` attribute, which can
capture material, color, fit, budget, or use-case information. It asks once more for
an additional must-have detail and then falls back to specific unasked attributes.

A Boundary response does not end clarification. The agent records specific declined
attributes and does not ask them again, while safely retrying the initial broad
question once because the customer may still have requirements in another dimension.

### Retrieval and reranking

Candidate generation uses several complementary routes:

1. a broad weighted OR query over category, constraints, and low-weight profile tags;
2. a category-conjunctive query; and
3. per-constraint conjunctive and disjunctive queries.

The union is reranked using explicit global features for category coverage, constraint
token coverage, exact normalized phrase matches, title overlap, price compatibility,
profile-tag overlap, and small rating/popularity tie-breakers. A holdout-validated
title-diversity pass reduces near-duplicate Top-10 results. Failed recommendations are
not repeated, which provides additional deterministic exploration over multiple turns.

Repeated FTS queries and normalized product signals are cached within the agent
process. The cache changes latency only; the underlying retrieval scores remain
deterministic.

## Model, Cost, and Privacy

- Model: none
- External API: none
- Network required during scoring: no
- Prompt/completion tokens: 0
- Estimated inference cost: $0
- Sensitive data sent externally: none

The final public evaluation completed in 42.23 seconds on the development machine.
That run covered 200 sessions and 451 calls to `respond`, or about 0.21 seconds per
session and 0.094 seconds per response end to end, including catalog loading and index
construction. Runtime varies with CPU and SQLite builds.

The system uses only the participant-visible aggregate profile fields and frozen
catalog metadata.

## Reproduction

Python 3.10 or later is recommended. The implementation was also verified with Python
3.9.6 and requires a Python build with SQLite FTS5 enabled.

```bash
python3 -m unittest -v
python3 -m evaluator.local_evaluator
python3 -m experiments.evaluate_split --split both
```

The evaluator writes the detailed report to `results.json`.

## Public-Set Result

Measured on the released 200-session public set:

| Metric | Weak starter | Submitted agent |
| --- | ---: | ---: |
| Hit Rate@10 | 0.125 | 0.995 |
| MRR | 0.068034 | 0.693675 |
| MTTC | 9.81 | 2.26 |
| Efficiency | 0.119 | 0.874 |
| TechnicalScore | 0.106710 | 0.880402 |

Scenario Hit Rate@10 is 1.0 for Browsing, Boundary, and Intent Override, and
0.9875 for Buying. Scenario MRR is 0.681939 for Browsing, 0.638333 for Boundary,
0.849299 for Intent Override, and 0.653968 for Buying. These are development-set
results and are not a guarantee of private-set performance.

## Demonstrated Interaction

```text
Customer: I'm looking for shoes and slippers, but I'm still exploring.
Agent:    [returns 10 candidates]
          What matters most to you—such as material, color, fit, budget,
          or intended use?
Customer: For that, what matters is: rubber sole; textile upper.
Agent:    [reranks using category + both constraints]
          Is there one more must-have detail I should prioritize?
```

The structured `ask_attribute` value is included on every clarification turn, and
recommendations contain ordered, catalog-valid `parent_asin` values.

## Limitations

- Products with identical category and boilerplate feature metadata can be impossible
  to distinguish without a more specific customer preference.
- Lexical FTS retrieval has limited synonym and conceptual matching compared with a
  dense retriever.
- The index is rebuilt for each agent process rather than persisted.
- Public-set tuning can overestimate private-set performance; no public target IDs or
  labels are embedded in the implementation.

## Team Contributions

Add the final team-member names and contribution breakdown before submission.
