# TechJam Conversational E-Commerce Search Challenge

Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

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

## Download the Catalog

Download `catalog.jsonl.gz` from the GitHub Release attached to this repository, then run:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify the downloaded file using the published `SHA256SUMS` file.

## Run the Starter

Python 3.10 or later is recommended. The starter uses only the Python standard library.

```bash
python3 -m evaluator.local_evaluator
```

Edit `starter/agent.py` to implement your system. Do not edit the evaluator or public labels when reporting your local score.
The command writes per-session results and aggregate metrics to `results.json`.

The included weak BM25 starter scores Hit Rate@10 `0.125`, MRR `0.068034`, and
MTTC `9.81` on the released public set. See `docs/baseline_results.json`.

## Included Hybrid Agent

`starter/agent.py` contains a stateful implementation with adaptive
clarification, intent-override handling, multi-route FTS5 retrieval, structured
reranking, holdout-validated title diversity, cached product signals, and
non-repeating recommendations. Its deterministic path uses only the Python standard
library and does not require network access or an API key. An optional rule-first
DeepSeek parser handles messages that do not match the known conversation templates.

Run its regression tests and public evaluation with:

```bash
python3 -m unittest -v
python3 -m evaluator.local_evaluator
```

The current public-set development result is Hit Rate@10 `0.995`, MRR `0.687145`,
MTTC `2.265`, and TechnicalScore `0.878343`. See
`docs/solution_report.md` for architecture, cost, limitations, and scenario results.

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
On the 200-session public set, forced `always` mode scored `0.862232` versus
`0.884461` for rule-first hybrid, used 236,537 tokens, and took 619.27 seconds.
Therefore `always` is an experimental rejected mode, not the recommended submission
configuration.

A recorded 40-session, scenario-stratified `always` audit produced 85 API-call
records, used 47,709 total API tokens, and cost an estimated `$0.0035`. Its
TechnicalScore was `0.899717`, below the matched deterministic control's `0.912208`.
The local JSONL export includes request payloads, raw and parsed responses, token-cache
counts, and latency, but never the API key or authorization header.

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

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  editable weak starter
evaluator/local_evaluator.py      public-set simulator and scorer
```

## Judging and Submission Policy

- Participant submission requirements: `docs/submission_rules.md`
- Organizer-only final judging controls: `organizer/JUDGING_RUNBOOK.md`
- Organizer private release checklist: `organizer/private_release_checklist.md`
- Judging day operations SOP: `organizer/JUDGING_DAY_SOP.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.
