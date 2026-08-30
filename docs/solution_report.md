# Offline Conversational Search Agent

## Summary

The submitted agent is a stateful hybrid shopping search system. It combines SQLite
FTS5 candidate retrieval with structured constraint reranking and an adaptive
clarification policy. Its default deterministic path requires no LLM, API key, network
access, model download, or third-party Python dependency. When configured, a
rule-first DeepSeek parser handles ambiguous or paraphrased messages.

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

### Intent parsing

Known simulator templates are parsed locally into Buying, Browsing, information,
override, Boundary, or no-information intents. If `DEEPSEEK_API_KEY` is present and
`DEEPSEEK_MODE=hybrid`, messages that do not match those high-confidence templates are
sent with a compact session-state summary to DeepSeek `deepseek-v4-flash`. The model
must return validated JSON containing the intent signal, shopping mode, typed
constraints, replacement attribute, declined attribute, and confidence. Invalid or
low-confidence output falls back to the local parser.

DeepSeek never selects product identifiers or searches the catalog. Only the validated
state update is passed to the deterministic retrieval and ranking stages. Structured
attribute replacement allows a paraphrased override to replace one preference while
preserving compatible constraints.

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

- Default model path: deterministic rules, no model
- Optional model: DeepSeek `deepseek-v4-flash` JSON chat completion
- External API: optional; disabled when `DEEPSEEK_API_KEY` is absent
- Network required during scoring: no, because all model failures fall back locally
- Offline public-run prompt/completion tokens: 0 / 0
- Offline public-run estimated inference cost: $0
- Optional API payload: current message plus compact category/preference/question state;
  catalog products and identifiers are never sent

The final offline public evaluation completed in 81.83 seconds on the development
machine. That run covered 200 sessions, including catalog loading and index
construction. Runtime varies with CPU, SQLite builds, and machine load. A forced
DeepSeek run on every turn took 619.27 seconds and reported 189,567 prompt plus 46,970
completion tokens. It reached Hit Rate 1.0 but reduced MRR to 0.619107 and
TechnicalScore to 0.862232, so this `always` configuration was rejected. Rule-first
`hybrid` remains the recommended mode.

A separate deterministic scenario-stratified 40-session audit recorded every model
request and response. It produced 85 API-call records, of which 83 passed strict
validation and two fell back to rules because the model returned an unsupported
attribute. The DeepSeek run scored Hit Rate 1.0, MRR 0.740724, MTTC 2.125, and
TechnicalScore 0.899717. The matched rule-only control scored 1.0, 0.779028, 2.075,
and 0.912208 respectively. Logged API usage was 38,197 prompt and 9,512 completion
tokens, with 32,896 prompt cache-hit tokens. Mean request latency was 1.1644 seconds
and estimated cache-aware cost was approximately $0.0035.

Setting `DEEPSEEK_LOG_PATH` enables the secret-free JSONL audit log. Each record
contains the compact intent request, raw and parsed response, token/cache counts, and
latency. Authorization headers and API keys are never written. The recommended export
directory, `artifacts/llm_exports/`, is ignored by Git.

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
| MRR | 0.068034 | 0.836357 |
| MTTC | 9.81 | 2.540 |
| Efficiency | 0.119 | 0.846 |
| TechnicalScore | 0.106710 | 0.917607 |

Scenario Hit Rate@10 is 1.0 for Browsing, Boundary, and Intent Override, and
0.9875 for Buying. Scenario MRR is 0.846488 for Browsing, 0.9 for Boundary,
0.882222 for Intent Override, and 0.801071 for Buying. These are development-set
results and are not a guarantee of private-set performance.

The same agent scores TechnicalScore 0.886642 on a 100-target audit disjoint from
the public set and 0.920732 on a second 100-target disjoint audit; both improve
over the pre-warmup agent by a margin comparable to the public gain, with no
Hit-Rate regression. Evidence-gated dynamic truncation ("warmup") is the change
that moved MRR from 0.687145 to 0.836357: while a session is under-informed (at
most two disclosed preferences, turn four or earlier), the agent returns only two
illustrative candidates and keeps clarifying instead of committing a full Top-10
that the evaluator would score at whatever rank the target happened to land.

## Demonstrated Interaction

```text
Customer: I'm looking for shoes and slippers, but I'm still exploring.
Agent:    [under-informed: returns 2 illustrative candidates, keeps clarifying]
          What matters most to you—such as material, color, fit, budget,
          or intended use?
Customer: For that, what matters is: rubber sole; textile upper.
Agent:    [enough evidence: reranks category + both constraints, returns full Top-10]
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
- The optional LLM path targets parsing coverage rather than canonical public
  templates. Forced use reduced public ranking quality, so value on a dedicated
  paraphrase suite remains unproven.

## Team Contributions

Add the final team-member names and contribution breakdown before submission.
