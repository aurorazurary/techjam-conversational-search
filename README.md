# TechJam Conversational E-Commerce Search Challenge

## Project Overview

This project is a stateful conversational shopping agent for the TechJam
Conversational E-Commerce Search Challenge. Given an anonymized preference profile
and a short customer message, it asks focused follow-up questions and recommends the
customer's hidden target product within at most 10 turns.

The solution combines conversation memory, Buying/Browsing intent handling, selective
preference replacement, adaptive clarification, SQLite FTS5 retrieval, structured
reranking, title diversity, and evidence-gated recommendation warmup. Its recommended
path is deterministic, uses only the Python standard library, and works without
network access. An optional DeepSeek parser is available for ambiguous or paraphrased
messages, but it never selects product identifiers or controls ranking.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer keeps 800 additional sessions private for final evaluation.

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Setup and Installation

### Prerequisites

- Python 3.10 or later is recommended. The implementation has also been exercised on
  Python 3.9.6.
- Python's SQLite build must include FTS5.
- Git and sufficient local disk space for the 50,000-product catalog.

Clone the repository and enter it:

```bash
git clone https://github.com/aurorazurary/techjam-conversational-search.git
cd techjam-conversational-search
```

The agent intentionally has no third-party runtime dependencies. Running the standard
installation command is still useful for a reproducible environment:

```bash
python3 -m pip install -r requirements.txt
python3 -c "import sqlite3; assert sqlite3.connect(':memory:').execute('select sqlite_compileoption_used(\"ENABLE_FTS5\")').fetchone()[0]"
```

### Download the catalog

Download `catalog.jsonl.gz` from the
[GitHub Releases page](https://github.com/aurorazurary/techjam-conversational-search/releases),
place it in the repository root, and verify the published checksum:

```bash
shasum -a 256 catalog.jsonl.gz
# Expected:
# 07fd142631fd6b03e2b4d09988c3eb7d53720e9d57010c79db48eeaada50a8f8
```

Extract it into the location used by the agent:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
test -s data/catalog.jsonl
```

`data/catalog.jsonl` and the compressed catalog are intentionally ignored by Git and
must not be committed. The canonical checksums are also recorded in
`data/SHA256SUMS`.

## Steps to Reproduce the Results

The accepted benchmark configuration is the default constructor configuration with
`DEEPSEEK_MODE=off`. This pins the deterministic intent path, requires no API key, and
prevents a caller's shell environment from silently changing the measured behavior.

### 1. Run the regression suite

```bash
DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m unittest -v
```

Expected result: `25` tests pass.

### 2. Evaluate the 200-session public set

```bash
DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m evaluator.local_evaluator \
  --output /tmp/techjam_public_results.json
```

### 3. Evaluate both frozen disjoint-target audits

```bash
DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m evaluator.local_evaluator \
  --dataset data/generalization_set.jsonl \
  --output /tmp/techjam_generalization_results.json

DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m evaluator.local_evaluator \
  --dataset data/category_gap_set.jsonl \
  --output /tmp/techjam_category_gap_results.json
```

Expected aggregate results for the accepted local configuration:

| Dataset | Sessions | Hit Rate@10 | MRR | MTTC | Efficiency | TechnicalScore |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Public | 200 | 0.995 | 0.836357 | 2.540 | 0.846 | 0.917607 |
| Generalization audit | 100 | 0.970 | 0.798806 | 2.900 | 0.810 | 0.886642 |
| Category-gap audit | 100 | 1.000 | 0.842440 | 2.600 | 0.840 | 0.920732 |

The two 100-session files are participant-created robustness audits with targets
disjoint from the public set and each other. They are not organizer private data or a
proxy for the private leaderboard. Runtime varies with CPU and SQLite build; the
metrics are deterministic for the catalog checksum above.

## Solution Architecture

`starter/agent.py` contains a stateful implementation with adaptive
clarification, intent-override handling, multi-route FTS5 retrieval, structured
reranking, holdout-validated title diversity, evidence-gated dynamic truncation
(short candidate lists while a session is still under-informed), cached FTS queries
and product signals, and non-repeating recommendations. Its deterministic path uses
only the Python standard library and does not require network access or an API key.
An optional rule-first DeepSeek parser handles messages that do not match the known
conversation templates.

See `progress.md` for the complete experiment history and
`docs/solution_report.md` for architecture, cost, limitations, and scenario-level
results.

### Optional DeepSeek intent parser

The API key is read only from the process environment. Never add it to source control.

```bash
export DEEPSEEK_API_KEY="your-key-from-your-secret-manager"
export DEEPSEEK_MODE=hybrid
python3 -m experiments.smoke_deepseek_intent
```

`hybrid` keeps the deterministic parser for recognized evaluator templates and calls
DeepSeek only for ambiguous messages. `always` calls DeepSeek on every turn for
experiments, while `off` guarantees network-free execution. Optional settings are
`DEEPSEEK_MODEL` (default `deepseek-v4-flash`), `DEEPSEEK_TIMEOUT_SECONDS` (default
`4.0`), `DEEPSEEK_MIN_CONFIDENCE` (default `0.55`), `DEEPSEEK_BASE_URL`, and
`DEEPSEEK_LOG_PATH`. The last setting writes one secret-free JSONL record per API call
for intent-parser auditing. Keep exports under `artifacts/llm_exports/`, which Git
ignores by default:

```bash
export DEEPSEEK_LOG_PATH="artifacts/llm_exports/deepseek_qna.jsonl"
```

DeepSeek failures, timeouts, empty output, invalid JSON, invalid attributes, and
low-confidence parses automatically fall back to the deterministic intent parser.
Forced `always` mode was tested on the public and both disjoint audit sets but scored
below the accepted deterministic configuration on all three, so it remains an
experimental diagnostic mode. Rejected-run metrics, token use, and latency are kept in
`progress.md`; the headline results above show only the best accepted configuration.

## Agent Interface

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` is one of `category`, `material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. See `docs/agent_api_contract.json`.

## Technical Metrics

- **Hit Rate@10:** fraction of sessions that find the target within 10 turns.
- **MRR:** mean reciprocal rank of the target; a miss contributes zero.
- **MTTC:** mean first-hit turn; a miss is assigned turn 11.
- **Reported token usage:** prompt and completion tokens returned by the team's model client.

```text
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency = clip((11 - MTTC) / 10, 0, 1)
```

`TechnicalScore` is an objective input to the `Technical Execution` assessment. It is not a separate judging criterion and does not represent the entire `Technical Execution` score.

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

Teams may use any legally accessible LLM API or local model. Teams manage their own credentials and must never commit API keys. Model choice, estimated cost, token usage, and latency must be disclosed. Token usage is a feasibility metric, not part of the core technical score. The organizer does not provide or reimburse model API credits; teams are responsible for any costs incurred through optional external services.

This implementation defaults to DeepSeek `deepseek-v4-flash` when the optional parser
is enabled. The public benchmark follows recognized templates, so the default hybrid
run makes no API calls and reports zero model tokens. Live-model cost and latency must
be measured and disclosed before relying on it for a submission. A forced live run is
documented in `progress.md`; it improved Hit Rate to 1.0 but reduced MRR and the overall
TechnicalScore, so the default remains rule-first hybrid.

## Limitations and Future Improvements

The current system is intentionally lightweight and reliable offline, but that choice
creates several limitations:

- **Lexical retrieval has semantic limits.** SQLite FTS5 is fast and transparent, but
  unfamiliar synonyms or conceptual matches may be missed without dense embeddings.
- **Some products are genuinely under-specified.** Near-identical products with the
  same category and boilerplate metadata cannot always be distinguished from the
  preferences the customer simulator reveals. One public Buying session remains a
  miss for this reason.
- **Natural-language robustness needs a dedicated test.** The public and participant
  audit sessions use canonical simulator wording. The optional DeepSeek path is meant
  for paraphrases, but forcing it on every canonical turn was slower and reduced MRR;
  its value on a frozen paraphrase suite is not yet proven.
- **Generalization evidence is still limited.** The two disjoint-target audits are
  participant-created, not organizer private data, and each is a single frozen seed
  rather than repeated cross-validated folds.
- **The index is rebuilt per process.** Startup could be improved by safely persisting
  and validating the FTS index for production use.

Given more time, we would first build a frozen paraphrase/state-transition suite and
category-grouped cross-validation folds. We would then evaluate a learned pairwise or
listwise reranker and lightweight semantic retrieval, retaining them only if they
improve both mean and worst-set TechnicalScore without reducing Hit Rate. Finally, we
would measure p50/p95 per-turn latency in a clean Python 3.10+ environment, explore a
persisted index, and improve customer-facing recommendation explanations.

## Files

```text
data/public_set.jsonl             200 labeled development sessions
data/generalization_set.jsonl     100 disjoint participant-created audit sessions
data/category_gap_set.jsonl       100 category-coverage audit sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
docs/devpost_project_description.md Devpost-ready project description
docs/solution_report.md           architecture, cost, results, and limitations
starter/agent.py                  agent entry point
evaluator/local_evaluator.py      public-set simulator and scorer
```

## Project Documentation

- Challenge behavior and metrics: `docs/competition_specification.md`
- Participant submission requirements: `docs/submission_rules.md`
- Full solution report: `docs/solution_report.md`
- Devpost description draft: `docs/devpost_project_description.md`
- Experiment history and current status: `progress.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.

## Member Contribution

**An Xiao**: Architectural design of the intent and preference system. Implement the soft preference mechanism

**Zhu Rong**: Designed and optimised the retrieval and reranking pipeline, including stateful FTS5 search, structured scoring, caching. Implemented the optional DeepSeek intent parser with strict validation and an offline fallback,

**Hao Rui**:Designed and implemented evidence-gated recommendation warmup, including configurable early result truncation, regression tests, parameter-sweep experiments, cross-dataset validation, and benchmark documentation. This substantially improved MRR and TechnicalScore without reducing public Hit Rate

**Xu Zhihan**:Fix state-handling bugs in override detection and attribute classification. Correct benchmark documentation and reproducibility issues for submission.

**Cao Yuewei**: Improved information gain from question category selection. Identified explicit user preference by distinguishing hard & soft requirements.
