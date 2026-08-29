# Project Progress

> Living handoff document for every coding agent and contributor. Read this file in
> full before planning or changing the project. Update it after every meaningful
> implementation/evaluation iteration.

## Current Status

- Last updated: 2026-08-29
- Branch: `main`
- Phase: 100-session disjoint-target generalization audit added and measured;
  rule-first `hybrid` retained
- Handoff state: the DeepSeek integration and organizer-compatible generalization
  fixture are verified locally on the main branch and currently uncommitted
- Agent entry point: `starter/agent.py`
- Test command: `python3 -m unittest -v`
- Evaluation command: `python3 -m evaluator.local_evaluator`
- Detailed local output: `results.json` (intentionally gitignored)
- Dependencies: Python standard library only; SQLite must include FTS5
- Network/API requirement: optional DeepSeek HTTPS API for ambiguous-message parsing;
  deterministic fallback requires no network or credentials
- Reported model tokens and estimated inference cost: hybrid public run 0 / $0;
  recorded 40-session `always` audit 47,709 API tokens / about $0.0035; rejected
  200-session `always` run 236,537 evaluator-reported tokens / at most about $0.040
- Catalog policy: `data/catalog.jsonl` and `starter/catalog.jsonl.gz` are local-only,
  ignored artifacts; obtain the catalog from the published release/checksum workflow

## Current Public-Set Benchmark

Final verified run on the released 200-session set:

| Metric | Weak baseline | Current agent | Change |
| --- | ---: | ---: | ---: |
| Hit Rate@10 | 0.125 | 0.995 | +0.870 |
| MRR | 0.068034 | 0.687145 | +0.619111 |
| MTTC | 9.81 | 2.265 | -7.545 |
| Efficiency | 0.119 | 0.8735 | +0.7545 |
| TechnicalScore | 0.106710 | 0.878343 | +0.771633 |

Scenario results:

| Scenario | Samples | Hit Rate@10 | MRR | MTTC |
| --- | ---: | ---: | ---: | ---: |
| Buying | 80 | 0.9875 | 0.637108 | 1.825 |
| Browsing | 80 | 1.0 | 0.670427 | 2.15 |
| Intent Override | 30 | 1.0 | 0.881429 | 3.866667 |
| Boundary | 10 | 1.0 | 0.638333 | 1.9 |

The current merged-main result was verified on all 200 sessions with zero model calls.
An earlier timed offline configuration took 81.83 seconds, including catalog loading
and index construction. The recorded 40-session live DeepSeek audit took 120.06
seconds and averaged 1.1644 seconds per API request.

## Frozen Generalization Audit

The participant-created `data/generalization_set.jsonl` contains 100 unique targets
from the frozen catalog with zero overlap with the 200 public targets. It deliberately
uses the organizer's participant-visible schema, scenario-to-difficulty mapping, exact
40 Buying / 40 Browsing / 15 Intent Override / 5 Boundary mix, and unchanged evaluator.
Hidden intent cards and simulator behavior are derived at runtime from catalog metadata
just as they are for the public set.

| Metric | Public 200 | Disjoint-target 100 | Change |
| --- | ---: | ---: | ---: |
| Hit Rate@10 | 0.995 | 0.970 | -0.025 |
| MRR | 0.687145 | 0.681409 | -0.005736 |
| MTTC | 2.265 | 2.700 | +0.435 |
| Efficiency | 0.8735 | 0.8300 | -0.0435 |
| TechnicalScore | 0.878343 | 0.855423 | -0.022920 |

The audit took 33.65 seconds, used zero model tokens, and missed three Browsing
sessions. It is not organizer data or an independent estimate of private performance:
profiles are safe public-profile samples and the simulator still uses canonical public
wording. Freeze this file for regression auditing; do not tune target-specific logic
against it.

## Implemented Architecture

- Per-session memory for category, constraints, profile tags, asked/declined
  attributes, initial preference, and previously recommended products.
- Modular `Intent -> PreferenceStore -> Ranker` architecture with hardness-weighted
  preferences and catalog-derived numerical/ordinal ranges.
- Optional rule-first DeepSeek `deepseek-v4-flash` intent parsing for ambiguous or
  paraphrased messages, strict JSON validation, selective attribute replacement,
  model-usage reporting, and automatic offline fallback.
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
- Holdout-validated greedy title diversity with strength `6.0` for less redundant
  Top-10 results and higher reciprocal rank.
- In-process caches for repeated FTS queries and normalized product signals.
- Deterministic non-repetition of failed recommendations across turns.
- Twenty-two regression tests covering evaluator behavior, state, caching, query
  expansion, splitting, DeepSeek requests, hybrid intent parsing, selective override,
  range determinism, organizer-compatible generalization data, and the agent.
- Reproduction, architecture, cost, interaction, and limitation documentation in
  `docs/solution_report.md`.

## Known Gaps and Next Improvements

Priorities are ordered by expected value and risk.

1. **Validate LLM value on paraphrases, not canonical templates.** The new 100-session
   audit changes target products but intentionally preserves the canonical simulator
   language, so it does not establish LLM value. A live 200-session
   `always` run was rejected: it recovered the single offline miss and slightly
   improved MTTC, but reduced MRR enough to lower TechnicalScore from 0.884461 to
   0.862232 while taking 7.57x longer. Keep rule-first `hybrid` as the default and build
   a frozen paraphrase suite before expanding the model trigger.
2. **Strengthen generalization evidence.** The disjoint-target audit scored 0.855423
   versus 0.878343 publicly and exposed three Browsing misses, but it is one
   participant-created seed with public-derived safe profiles. Keep it frozen and add
   repeated scenario-stratified catalog seeds or grouped category folds before another
   high-dimensional tuning effort.
3. **Improve ambiguous Buying recall without sacrificing MRR.** One public Buying
   session remains a miss because its disclosed category and features are shared by a
   large group of near-identical novelty products. Title diversity improved MRR but
   did not recover this fundamentally under-specified target. Do not hard-code it.
4. **Test a genuinely learned reranker.** The scorer now exposes explicit features,
   but the first hand-calibrated weight variant was rejected. Use cross-validated
   pairwise/listwise learning and export only global weights if it beats the accepted
   default across folds.
5. **Test retrieval robustness.** Add tests for prices, empty/unknown queries,
   duplicate constraints, malformed-but-valid input, sparse catalog rows, and all
   allowed clarification attributes.
6. **Consider offline semantic retrieval only if justified.** Basic synonym expansion
   was tested and rejected for a small score regression. Dense embeddings may still
   help novel paraphrases, but they add dependencies, assets, startup time, and
   submission risk. Keep the standard-library lexical fallback fully functional.
7. **Finish submission metadata.** Add team-member contribution details, confirm the
   organizer's runtime limits, and package the final entry point and instructions.
8. **Validate the recommended runtime.** The current code works with local Python
   3.9.6, but the challenge recommends Python 3.10+. Run the final bundle in a clean
   Python 3.10+ environment.

## Guardrails

- Do not edit the evaluator or public labels to improve reported scores.
- Do not use or hard-code `ground_truth`, public target IDs, hidden intent cards, or
  scenario labels inside the agent.
- Do not commit API keys, secrets, private evaluation data, or generated catalog data.
- Do not force-add `data/catalog.jsonl` or `starter/catalog.jsonl.gz`; both catalog
  artifacts must remain outside Git.
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

### Iteration 4 — Holdout harness, feature refactor, and latency caches

- Date/agent: 2026-08-29 / Codex
- Status: accepted
- Hypothesis: a scenario-stratified holdout will make ranking experiments safer, and
  caching repeated FTS results/product normalization will reduce latency without
  changing metrics.
- Changes and files: added `experiments/evaluate_split.py`, explicit reranker features,
  FTS/product-signal caches, experiment controls, and split regression tests.
- Tests/commands: `python3 -m unittest -v`; control development evaluation before and
  after refactor; exact metric comparison.
- Before metrics: development TechnicalScore 0.856955; projected proportional runtime
  about 87.7 seconds for 150 sessions.
- After metrics: development TechnicalScore unchanged at 0.856955; runtime 32.21
  seconds for 150 sessions.
- Per-scenario effects: none; all metrics were identical.
- Runtime/cost effects: approximately 63% lower development runtime; tokens/cost remain
  zero.
- Findings and risks: cache memory grows with encountered products and FTS queries but
  remained safe for the 50,000-product public catalog.
- Next recommended action: tune only global diversity/weight controls on development.

### Iteration 5 — Ranking, question, and semantic experiments

- Date/agent: 2026-08-29 / Codex
- Status: title diversity accepted; other variants rejected
- Hypothesis: reducing near-duplicate titles in the Top 10 will improve MRR on
  ambiguous candidate sets without reducing Hit Rate.
- Changes and files: added optional title-diversity selection, reranker-weight,
  broad-question, and synonym-expansion controls plus a cached diversity sweep tool.
- Tests/commands: development control and variants; diversity sweep at strengths 0.5,
  1, 2, 3, 4, 5, 6, and 8; one holdout run for the selected strength; final official
  public evaluator; 13/13 unit tests.
- Before metrics: full TechnicalScore 0.862987, MRR 0.626956, MTTC 2.13, runtime
  116.94 seconds. Split control was development 0.856955 and holdout 0.881081.
- After metrics: strength `6.0` produced development 0.871136 and holdout 0.908200.
  Full TechnicalScore is 0.880402, MRR 0.693675, MTTC 2.26, Hit Rate 0.995, runtime
  42.23 seconds.
- Per-scenario effects: full MRR is Buying 0.653968, Browsing 0.681939, Intent Override
  0.849299, and Boundary 0.638333. Scenario Hit Rates are unchanged.
- Runtime/cost effects: 64% lower full runtime despite diversity selection; zero API
  cost and tokens.
- Findings and risks: stronger hand-set title/exact weights (0.845414), one broad
  question (0.843467), and synonym expansion (0.855397) all regressed development and
  were rejected. Diversity improves MRR but modestly worsens MTTC and is tuned on one
  small split.
- Next recommended action: use repeated stratified folds before attempting a learned
  global reranker; do not reopen rejected variants without a narrower hypothesis.

### Iteration 6 — Decouple seen_recommendations from OverrideIntent

- Date/agent: 2026-08-29 / Claude
- Status: accepted
- Hypothesis: `seen_recommendations` only cleared when a message was classified as
  `OverrideIntent`. If the private evaluator phrases an override differently than
  `OVERRIDE_RE`/`"actually, ignore"` expects, the correct target can be shown pre-override
  (excluded per the scoring rule below), then stay permanently excluded for the rest of
  the session even after the real preference is disclosed.
- Why this matters: a pre-override recommendation never counts as a hit (only credited
  once the override turn has been sent), but it still gets added to
  `seen_recommendations`. If detection later fails, that correct product can never be
  recommended again.
- Changes and files: `starter/Ranker.py` — `apply_intent()` now clears
  `seen_recommendations` whenever any branch actually adds new state (tracked via a
  `changed` flag using `add_preference`'s existing return value), not only inside the
  `OverrideIntent` branch. The override branch always sets `changed = True` even if its
  value duplicates something already disclosed.
- Tests/commands: `python -m unittest discover -s tests -v`; `python -m evaluator.local_evaluator`.
- Before metrics: TechnicalScore 0.884461, HR@10 0.995.
- After metrics: TechnicalScore 0.87811, HR@10 0.995. `intent_override` unchanged
  (HR 1.0, MRR 0.881429, MTTC 3.867 — identical to before).
- Per-scenario effects: small MRR dip in buying/browsing (broader clearing also fires on
  ordinary disclosure turns); no scenario's HitRate changed.
- Findings and risks: not verified under a fair wording-robustness test (an attempted
  perturbed-evaluator check broke an unrelated shared regex and produced unusable
  results). Intent classification itself is still regex-based and known-fragile; a
  planned LLM-based intent classifier is expected to reduce how often this path is
  needed, but the fallback structure here stays useful regardless of how intent gets
  classified.
- Next recommended action: re-run a properly scoped wording-robustness check (perturb
  only override phrasing, leave other regex anchors like `MATTERS_RE` untouched) once
  time allows.

### Iteration 7 — Hybrid DeepSeek intent parsing

- Date/agent: 2026-08-29 / Codex
- Status: implemented; offline path accepted, live-model validation pending
- Hypothesis: rule-first DeepSeek parsing will improve robustness to private-set
  paraphrases and selective overrides without reducing canonical offline metrics when
  the API is unavailable.
- Changes and files: added a standard-library DeepSeek JSON client, injectable hybrid
  intent generator, compact session context, strict enum/confidence validation,
  structured attribute replacement, token propagation, runtime smoke command,
  merged-architecture compatibility proxies, and deterministic range selection.
- Tests/commands: `python3 -m unittest -v` (19/19 passed); mocked request, fallback,
  context, usage, override, and range tests; full evaluator with
  `PYTHONHASHSEED=2`; `git diff --check`.
- Before metrics: freshly measured merged local baseline Hit Rate 0.995, MRR 0.705536,
  MTTC 2.235, TechnicalScore 0.884461.
- After metrics: offline hybrid fallback Hit Rate 0.995, MRR 0.705536, MTTC 2.235,
  TechnicalScore 0.884461; zero prompt/completion tokens.
- Per-scenario effects: unchanged at Buying 0.666086 MRR, Browsing 0.687426, Intent
  Override 0.881429, and Boundary 0.638333; scenario Hit Rates unchanged.
- Runtime/cost effects: final offline run 81.83 seconds and $0. Live DeepSeek latency,
  token use, and cost were not measured because the secret was intentionally not
  persisted or placed in a command.
- Findings and risks: public templates are handled by high-confidence rules, so hybrid
  mode makes zero API calls on the public evaluator. The LLM path targets paraphrase
  robustness, not the canonical public score. Official scoring may disable network,
  and model behavior is not accepted until a separate paraphrase/live evaluation.
- Next recommended action: export `DEEPSEEK_API_KEY` from a secret manager, run
  `python3 -m experiments.smoke_deepseek_intent`, then evaluate a frozen paraphrase
  suite in `hybrid` and `always` modes without changing the public evaluator.

### Iteration 8 — Live DeepSeek forced-mode evaluation

- Date/agent: 2026-08-29 / Codex
- Status: `always` mode rejected; `hybrid` mode remains current
- Hypothesis: forcing DeepSeek intent parsing on every canonical turn may improve
  Buying/Browsing interpretation, intent replacement, early conversion, and ranking.
- Changes and files: no ranking/parser code changes; ran a live smoke test followed by
  the unchanged 200-session evaluator with `DEEPSEEK_MODE=always`. The credential was
  stored only in a permission-restricted temporary file, removed immediately after the
  run, and never added to Git.
- Tests/commands: `python3 -m experiments.smoke_deepseek_intent`; full evaluator with
  `PYTHONHASHSEED=2`; session-level comparison against the final offline result.
- Before metrics: hybrid/offline Hit Rate 0.995, MRR 0.705536, MTTC 2.235,
  TechnicalScore 0.884461, runtime 81.83 seconds, zero tokens.
- After metrics: forced DeepSeek Hit Rate 1.0, MRR 0.619107, MTTC 2.175,
  TechnicalScore 0.862232, runtime 619.27 seconds, 236,537 reported tokens.
- Per-scenario effects: Buying MRR 0.589484, Browsing 0.581930, Intent Override
  0.778611, and Boundary 0.675000. All scenario Hit Rates reached 1.0. MTTC was Buying
  1.625, Browsing 2.05, Intent Override 3.866667, and Boundary 2.5.
- Runtime/cost effects: 435 API attempts; average 435.8 prompt and 108.0 completion
  tokens per response; 7.57x offline runtime. An all-input-cache-miss upper estimate at
  current DeepSeek V4 Flash pricing is approximately $0.0397; actual billing may be
  lower because cache-hit tokens were not retained by the evaluator.
- Findings and risks: reciprocal rank improved in 36 sessions, worsened in 62, and was
  unchanged in 102. Thirty-two sessions hit earlier, 28 later, and 140 on the same
  turn. The model recovered the one offline miss with no hit-to-miss regressions, but
  ranking loss dominated the small Hit Rate/MTTC gains. Canonical templates are better
  handled by deterministic rules.
- Next recommended action: retain `hybrid`, create a frozen paraphrase-only test set,
  and trigger DeepSeek only when no high-confidence rule matches. Do not use `always`
  for official scoring.

### Iteration 9 — Recorded 40-session LLM audit

- Date/agent: 2026-08-29 / Codex
- Status: completed; export retained locally and `always` remains rejected
- Hypothesis: a bounded, scenario-stratified live run with per-call records will make
  DeepSeek behavior, validation failures, latency, cache use, and cost auditable
  without exposing credentials or changing the accepted ranking pipeline.
- Changes and files: added opt-in secret-free JSONL request/response logging to
  `starter/deepseek_client.py`; added `DEEPSEEK_LOG_PATH` documentation and ignored
  `artifacts/llm_exports/`; exposed `--holdout-fraction` in
  `experiments/evaluate_split.py`; added logging and exact 40-session split tests.
- Tests/commands: `python3 -m unittest -v` (20/20 passed); live `always` evaluation on
  the deterministic scenario-stratified 20% holdout; matched rule-only control;
  JSONL/schema, secret-scan, Git-ignore, temporary-credential, and diff checks.
- Before metrics: matched rule-only 40-session control Hit Rate 1.0, MRR 0.779028,
  MTTC 2.075, Efficiency 0.8925, TechnicalScore 0.912208, runtime 15.76 seconds.
- After metrics: recorded DeepSeek 40-session run Hit Rate 1.0, MRR 0.740724,
  MTTC 2.125, Efficiency 0.8875, TechnicalScore 0.899717, runtime 120.06 seconds.
- Per-scenario effects: DeepSeek versus rules MRR was Buying 0.748437 versus 0.764757,
  Browsing 0.778373 versus 0.805729, Intent Override 0.783333 versus 0.916667, and
  Boundary 0.250000 versus 0.266667. All scenario Hit Rates remained 1.0.
- Runtime/cost effects: 85 logged API calls; 38,197 prompt and 9,512 completion tokens
  (47,709 total), including 32,896 prompt cache-hit and 5,301 cache-miss tokens. Mean,
  median, p95, and maximum latency were 1.1644, 1.1233, 1.5316, and 2.1688 seconds.
  Estimated cache-aware cost was approximately $0.0035 at the pricing used for this
  audit. The evaluator reported 46,677 accepted tokens; the 1,032-token difference is
  from two invalid model outputs that were logged but correctly fell back to rules.
- Findings and risks: 83 records passed strict validation; two returned unsupported
  `fabric` attributes and fell back safely. The export contains request payloads, raw
  and parsed responses, token/cache counts, and latency, but no authorization header
  or API key. The temporary credential was removed, and all export files are ignored
  by Git. Forced LLM parsing again reduced ranking quality relative to rules.
- Next recommended action: use the same logger on a frozen paraphrase-only suite in
  default `hybrid` mode; do not expand the trigger or use `always` for official scoring
  unless cross-validated results beat the deterministic parser.

### Iteration 10 — Main-branch integration validation

- Date/agent: 2026-08-29 / Codex
- Status: accepted on `main`
- Hypothesis: integrating the DeepSeek parser and audit logger with the remote-main
  recommendation-reset fix will preserve its wording robustness while retaining a
  network-free canonical evaluation path.
- Changes and files: rebased the verified implementation onto current `origin/main`;
  resolved `starter/Ranker.py` by retaining signal-based LLM intents, selective
  attribute replacement, and remote main's `changed`-based clearing of previously
  recommended products; retained and renumbered both branches' progress history.
- Tests/commands: `python3 -m unittest -v` (20/20 passed); full 200-session evaluator
  with `PYTHONHASHSEED=2`; `git diff --check`; tracked-artifact and credential scans.
- Before metrics: remote-main Iteration 6 reported Hit Rate 0.995 and TechnicalScore
  0.878110 after generalizing recommendation resets.
- After metrics: Hit Rate 0.995, MRR 0.687145, MTTC 2.265, Efficiency 0.8735, and
  TechnicalScore 0.878343; zero prompt and completion tokens in default hybrid mode.
- Per-scenario effects: Buying Hit Rate 0.9875, MRR 0.637108, MTTC 1.825; Browsing
  1.0, 0.670427, 2.15; Intent Override 1.0, 0.881429, 3.866667; Boundary 1.0,
  0.638333, 1.9.
- Runtime/cost effects: no API calls and $0 model cost on canonical templates; this
  verification run was not externally timed.
- Findings and risks: the merged implementation slightly improves the recorded
  remote-main TechnicalScore while preserving its broader reset behavior. It remains
  below the earlier pre-merge feature score because ordinary new information can
  reopen previously shown candidates; this tradeoff is documented rather than hidden.
- Next recommended action: evaluate the generalized reset policy with multiple frozen
  override-paraphrase folds before deciding whether its robustness gain justifies the
  MRR tradeoff.

### Iteration 11 — Organizer-compatible 100-session generalization audit

- Date/agent: 2026-08-29 / Codex
- Status: accepted as a frozen audit fixture; no agent tuning performed
- Hypothesis: 100 catalog-valid targets disjoint from the public 200, evaluated through
  the unchanged organizer simulator, will expose target-level overfitting while
  preserving comparable session behavior and metrics.
- Changes and files: added deterministic
  `experiments/generate_generalization_set.py`, frozen
  `data/generalization_set.jsonl`, contract tests in
  `tests/test_generalization_set.py`, and reproduction/disclosure documentation in
  `README.md` and `data/README.md`.
- Tests/commands: generator validation; focused 2/2 tests; unchanged local evaluator
  with `PYTHONHASHSEED=2`; JSONL schema/mix/uniqueness/disjointness checks; full suite
  and diff checks.
- Before metrics: current public Hit Rate 0.995, MRR 0.687145, MTTC 2.265,
  Efficiency 0.8735, TechnicalScore 0.878343.
- After metrics: disjoint-target Hit Rate 0.970, MRR 0.681409, MTTC 2.700,
  Efficiency 0.8300, TechnicalScore 0.855423.
- Per-scenario effects: Buying 40 samples, Hit Rate 1.0, MRR 0.727222, MTTC 1.75;
  Browsing 40, 0.925, 0.634087, 3.025; Intent Override 15, 1.0, 0.694048,
  4.133333; Boundary 5, 1.0, 0.655556, 3.4.
- Runtime/cost effects: 33.65 seconds for 100 sessions; zero prompt/completion tokens
  and $0 model cost in the default offline/hybrid path.
- Findings and risks: all 100 targets are catalog-valid, unique, and absent from the
  public target set; all three misses were Browsing. The fixture exactly matches the
  public schema and scenario policy but is not organizer or private data. It reuses
  safe aggregate profile examples and canonical simulator phrasing, so it measures
  target/retrieval generalization rather than natural-language paraphrase robustness.
- Next recommended action: keep this seed untouched as a regression audit, build a
  separate labeled paraphrase suite for intent/state accuracy, and use additional
  generated seeds—not this frozen file—for development experiments.

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
