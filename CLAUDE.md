# CLAUDE.md — Project Context for Claude Code

Context handoff for TikTok TechJam 2026, Track 4. Read this first, then `docs/competition_specification.md`, `docs/agent_api_contract.json`, and `starter/agent.py`.

---

## Team & Repo

- **Team:** Manbobobo — Hao Rui, Zhu Rong, Xu Zhihan, Cao Yuewei, An Xiao
- **Repo:** forked from `TechJam2026/techjam-conversational-search` into the team's account (owner `aurorazurary`). Everyone works on this one fork; teammates are collaborators.
- **Track:** 4 — Shopping Copilot: AI Conversational Search & Recommendations.

---

## The Task

Build a conversational shopping agent. Each session has **one hidden target product**; the agent must get it into its **Top-10 recommendations** within **at most 10 turns**, as early and as highly ranked as possible. Each turn the agent may ask a clarification question, return a ranked list of up to 10 `parent_asin` values, or both.

The evaluator imports the agent and runs it **locally** — no web server, no hosted API, no port. You submit a Python agent, not a service.

---

## Environment (already set up and verified)

- Python 3.10+; kit is **standard-library only** — no `pip install` needed for the baseline.
- Catalog (`catalog.jsonl.gz`, ~50K products) downloaded from the repo **Release** (not in Git), verified against `SHA256SUMS`, unzipped to `data/catalog.jsonl`.
- Baseline runs with: `python3 -m evaluator.local_evaluator` → writes `results.json`.
- **Data and secrets must never be committed.** `.gitignore` must cover `data/catalog.jsonl`, `catalog.jsonl.gz`, `results.json`, `.env`. Check `git status` before every commit — `catalog.jsonl` must not appear. Each teammate downloads the catalog themselves; it never goes through Git.

---

## Key Files

```
starter/agent.py                  <-- the ONLY file we edit to build the agent
evaluator/local_evaluator.py      public-set simulator + scorer (do NOT edit for reported scores)
data/public_set.jsonl             200 labeled dev sessions
data/catalog.jsonl                50K frozen products (downloaded, gitignored)
docs/agent_api_contract.json      machine-readable Agent contract
docs/competition_specification.md full rules + evaluation protocol
docs/evaluation_config.json       scoring config
docs/baseline_results.json        reference baseline score
```

---

## Agent Interface (the contract — keep it stable, swap internals behind it)

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",   # or null
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` must be one of: `category, material, color, size, style, brand, budget, feature, use_case, other, null`.

Only exact `parent_asin` equality counts as a hit. Only the first 10 unique, catalog-valid IDs are scored; duplicates and invalid IDs are dropped. Max 10 turns.

---

## Scoring

```
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency     = clip((11 - MTTC) / 10, 0, 1)
```

- **HitRate@10** — fraction of sessions where target lands in scored Top 10 (accuracy; weighted highest).
- **MRR** — mean reciprocal rank of target; miss = 0.
- **MTTC** — mean first-hit turn; miss = 11.
- Metrics also reported per scenario. Token usage is a **feasibility** metric only, NOT in the technical score.

Four scenario types: **Buying 40%, Browsing 40%, Intent Override 15%, Boundary 5%.**

---

## Baseline Result (weak BM25 starter, reproduced and confirmed)

Overall: HitRate@10 **0.125** · MRR **0.068034** · MTTC **9.81** · Efficiency 0.119 · TechnicalScore **0.10671**.

Per-scenario breakdown (this is the map of where the points are):

| Scenario | n | HR@10 | MRR | MTTC | Read |
| --- | --- | --- | --- | --- | --- |
| buying | 80 | 0.2375 | 0.127 | 8.6 | Only scenario doing okay — hard constraint stated early, BM25 catches it. Least upside. |
| browsing | 80 | 0.025 | 0.0045 | 10.75 | **Near-zero, 40% of sessions. Biggest opportunity.** Vague openings; BM25 with no clarification has nothing to match. |
| intent_override | 30 | 0.133 | 0.104 | 10.07 | No state → concatenates contradictory terms when customer changes mind. |
| boundary | 10 | 0.0 | 0.0 | 11.0 | Never hits. Small weight (5%), lowest priority. |

---

## Build Plan (priority order, driven by the breakdown above)

Do 1–3 before 4. A clean agent that finishes beats a fancy one that doesn't. A valid submission should be possible by day 3.

1. **Browsing → add clarification (highest leverage).** When the opening is vague / candidate pool is huge, ask a question (`ask_attribute`) that most shrinks the pool instead of blindly ranking. Owner: Xu Zhihan.
2. **Intent Override → add conversation state.** Track slots (color, style, material, budget); **replace** a slot when the customer changes intent, don't append/concatenate. Owner: Zhu Rong.
3. **Buying → strengthen retrieval.** Improve BM25 over catalog fields (`title`, `features`, `details`, `description`, `categories`); already the strongest, incremental gains. Owner: Hao Rui.
4. **Boundary → handle "no preference" gracefully.** Accept the answer, stop asking, don't invent constraints. Last. 
5. **If time:** hybrid retrieval (BM25 + dense embeddings), LLM reranking over top candidates. Owner: An Xiao. Eval harness & analysis: Cao Yuewei.

---

## LLM Policy

Not required — a strong score is reachable on retrieval + state + clarification alone. External LLM APIs are allowed but the team manages its own keys/costs, must disclose usage, and **must never commit API keys**. The agent itself must be Python.

---

## Workflow

- `main` stays runnable — the evaluator must pass on it.
- Feature branches per workstream (`clarification`, `dialog-state`, `retrieval-bm25`, `eval-harness`); PR into `main`.
- Every PR reports a **before/after evaluator score** (overall + per-scenario).
- Everyone runs the same local evaluator so scores are comparable.

---

## Immediate Next Step for Claude Code

Open `starter/agent.py` and inspect how `reset` and `respond` currently work, and read the first couple of sessions in `data/public_set.jsonl` to confirm the exact `user_profile` / message shape. Then start with workstream 1 (browsing clarification), re-running `python3 -m evaluator.local_evaluator` after each change and watching the per-scenario `browsing` numbers.

---

## Submission (deadlines)

72-hour window: **29 Aug 12pm → 1 Sep 12pm** (Devpost; late = rejected). Finalists announced 8 Sep; Grand Final 11 Sep at TikTok Singapore (finalists generally expected in person).

Deliverables: public repo + README, Devpost written description (tools/APIs/libraries/datasets), demo or walkthrough video (YouTube, public, linked on Devpost). All 5 members must register on **both** the Registration Form and Devpost by 1 Sep 12pm. No secrets anywhere in repo/history.
