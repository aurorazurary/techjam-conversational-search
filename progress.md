# Project Progress

> Living handoff document for every coding agent and contributor. Read this file in
> full before planning or changing the project. Update it after every meaningful
> implementation/evaluation iteration.

## Current Status

- Last updated: 2026-08-29
- Branch: `feature/stateful-conversational-agent`
- Phase: stateful offline agent implemented; public-set validation complete
- Handoff state: implementation, tests, reports, and agent-context files are included
  in the feature branch commit
- Agent entry point: `starter/agent.py`
- Test command: `python3 -m unittest -v`
- Evaluation command: `python3 -m evaluator.local_evaluator`
- Detailed local output: `results.json` (intentionally gitignored)
- Dependencies: Python standard library only; SQLite must include FTS5
- Network/API requirement: none
- Reported model tokens and estimated inference cost: 0 / $0

## Current Public-Set Benchmark

Final verified run on the released 200-session set:

| Metric | Weak baseline | Current agent | Change |
| --- | ---: | ---: | ---: |
| Hit Rate@10 | 0.125 | 0.995 | +0.870 |
| MRR | 0.068034 | 0.626956 | +0.558922 |
| MTTC | 9.81 | 2.13 | -7.68 |
| Efficiency | 0.119 | 0.887 | +0.768 |
| TechnicalScore | 0.106710 | 0.862987 | +0.756277 |

Scenario results:

| Scenario | Samples | Hit Rate@10 | MRR | MTTC |
| --- | ---: | ---: | ---: | ---: |
| Buying | 80 | 0.9875 | 0.597475 | 1.6625 |
| Browsing | 80 | 1.0 | 0.599658 | 1.9875 |
| Intent Override | 30 | 1.0 | 0.768704 | 3.8 |
| Boundary | 10 | 1.0 | 0.655952 | 2.0 |

The final timed evaluation took 116.94 seconds for 200 sessions and 425 calls to
`respond` (approximately 0.58 seconds per session and 0.28 seconds per response,
including catalog loading and index construction).

## Implemented Architecture

- Per-session memory for category, constraints, profile tags, asked/declined
  attributes, initial preference, and previously recommended products.
- Adaptive structured clarification using `ask_attribute`, beginning with a broad
  must-have question and falling back to specific attributes.
- Boundary handling that avoids repeatedly asking declined specific attributes while
  allowing one safe retry of the broad question.
- Intent-override handling that removes the superseded initial preference, retains
  compatible facts, and reopens products that were unscoreable before the override.
- In-memory SQLite FTS5 index over title, category, features, details, store, and
  description.
- Multi-route candidate generation using broad OR, category AND, and per-constraint
  AND/OR searches.
- Structured reranking using category coverage, constraint coverage, exact normalized
  phrases, title overlap, price compatibility, profile tags, ratings, and popularity.
- Deterministic non-repetition of failed recommendations across turns.
- Eight regression tests covering evaluator behavior and the new stateful agent.
- Reproduction, architecture, cost, interaction, and limitation documentation in
  `docs/solution_report.md`.

## Known Gaps and Next Improvements

Priorities are ordered by expected value and risk.

1. **Protect private-set generalization.** Create a deterministic development/holdout
   split inside the 200 public sessions for future tuning. Report holdout results as
   well as full-public results, and never embed public target IDs or labels in agent
   logic.
2. **Improve ambiguous Buying recall without sacrificing MRR.** One public Buying
   session remains a miss because its disclosed category and features are shared by a
   large group of near-identical novelty products. Test principled diversification
   (for example title-cluster or metadata-template diversity) against a holdout before
   adopting it. Do not hard-code the missed product.
3. **Reduce latency.** Profile candidate queries and reranking. Consider caching query
   signatures, reducing redundant FTS routes, storing normalized metadata once, or
   persisting the catalog index. Preserve the current score while optimizing.
4. **Test retrieval robustness.** Add tests for prices, empty/unknown queries,
   duplicate constraints, malformed-but-valid input, sparse catalog rows, and all
   allowed clarification attributes.
5. **Consider offline semantic retrieval only if justified.** Dense embeddings may
   improve synonyms, but they add dependencies, assets, startup time, and submission
   risk. Keep the standard-library lexical fallback fully functional.
6. **Finish submission metadata.** Add team-member contribution details, confirm the
   organizer's runtime limits, and package the final entry point and instructions.
7. **Validate the recommended runtime.** The current code works with local Python
   3.9.6, but the challenge recommends Python 3.10+. Run the final bundle in a clean
   Python 3.10+ environment.

## Guardrails

- Do not edit the evaluator or public labels to improve reported scores.
- Do not use or hard-code `ground_truth`, public target IDs, hidden intent cards, or
  scenario labels inside the agent.
- Do not commit API keys, secrets, private evaluation data, or generated catalog data.
- Keep the required `Agent.reset(...)` and `Agent.respond(...)` contract intact.
- Only catalog-valid, unique `parent_asin` values in the first 10 recommendations are
  scored.
- Preserve a network-free fallback suitable for official scoring.
- Treat public metrics as development evidence, not a private-set guarantee.

## Required Iteration Workflow

Every meaningful iteration must follow this loop:

1. Read this file and inspect `git status` before making changes.
2. State one hypothesis and the metric or behavior expected to improve.
3. Make the smallest generalizable change; do not tune to a specific target ID.
4. Run focused tests, then the full unit suite.
5. Run the evaluator when ranking/session behavior changes.
6. Compare overall and per-scenario metrics with the last accepted result.
7. Update **Current Status**, **Known Gaps**, and append an **Iteration Log** entry
   before ending the work session.

Never delete or rewrite prior iteration log entries. If an experiment is rejected or
reverted, record that result so another agent does not repeat it.

## Iteration Log

### Iteration 0 — Weak BM25 baseline

- Status: completed
- Agent behavior: stateless BM25 over only the latest user message; no structured
  clarification and no conversation memory.
- Result: Hit Rate@10 0.125, MRR 0.068034, MTTC 9.81, TechnicalScore 0.106710.
- Finding: generic post-miss feedback replaced useful query context, and
  `ask_attribute=None` prevented the simulator from revealing constraints.

### Iteration 1 — Stateful clarification and hybrid reranking

- Status: completed
- Hypothesis: retaining category/constraints and asking structured must-have questions
  will primarily improve Browsing and Boundary sessions.
- Changes: added session state, broad and specific clarification, multi-route FTS5
  retrieval, exact/structured reranking, profile tags, price scoring, and non-repeating
  recommendations.
- Verification: full 200-session evaluator run.
- Result: Hit Rate@10 0.985, MRR 0.599790, MTTC 2.31, TechnicalScore 0.846237.
- Finding: Browsing and Boundary reached 1.0 Hit Rate, but two Intent Override sessions
  failed because all earlier constraints were discarded at the override.

### Iteration 2 — Selective intent replacement

- Status: accepted and current
- Hypothesis: remove only the superseded initial preference while retaining compatible
  constraints, and reopen previously recommended products after the override.
- Changes: selective override state update plus regression coverage for override,
  Boundary, memory, reranking, non-repetition, and contract safety.
- Verification: 8/8 unit tests passed; deterministic full evaluator rerun passed;
  `git diff --check` passed.
- Result: Hit Rate@10 0.995, MRR 0.626956, MTTC 2.13, TechnicalScore 0.862987.
- Finding: all Intent Override sessions now hit. One metadata-ambiguous Buying session
  remains a miss; hard-coding it was explicitly rejected.

### Iteration 3 — Persistent agent handoff context

- Date/agent: 2026-08-29 / Codex
- Status: accepted and current
- Hypothesis: a mandatory read-first and update-after-iteration handoff will prevent
  Codex and Claude from losing benchmark context or repeating rejected experiments.
- Changes and files: created `progress.md`, root `AGENTS.md`, and root `CLAUDE.md` with
  shared startup, verification, history-preservation, and iteration-update rules.
- Tests/commands: inspected all three rendered files; `git diff --check` passed.
- Before metrics: TechnicalScore 0.862987.
- After metrics: unchanged; this iteration does not modify agent behavior.
- Per-scenario effects: none.
- Runtime/cost effects: none.
- Findings and risks: instructions rely on each tool honoring its conventional root
  instruction file; contributors should still point new automation to `progress.md`.
- Next recommended action: create a deterministic public development/holdout split
  before the next ranking experiment.

## Template for the Next Iteration

Copy this section to the bottom of the log and fill every field:

```markdown
### Iteration N — Short descriptive name

- Date/agent:
- Status: proposed | running | accepted | rejected | reverted
- Hypothesis:
- Changes and files:
- Tests/commands:
- Before metrics:
- After metrics:
- Per-scenario effects:
- Runtime/cost effects:
- Findings and risks:
- Next recommended action:
```
