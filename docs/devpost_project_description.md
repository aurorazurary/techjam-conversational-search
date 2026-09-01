# Devpost Project Description

## Project title

**TechJam Conversational Product Search Agent**

## Short description

Our deliverable, Manbobobo,  is a stateful shopping assistant that asks focused follow-up questions, remembers and
updates customer preferences, and retrieves and reranks products from a 50,000-item
catalog. It combines fast offline lexical retrieval with structured conversational
reasoning and an optional LLM parser for unconventional situations.

## Inspiration and problem statement

Our solution was inspired by some unique challlenges that we identified in the product recommendation.

First, A useful shopping agent must adapt to capricious customer demands.They can be ready to buy, still exploring, changing their mind, or unable to provide a preference for aparticular attribute. Accurate prediction of customer intents are necessary for satisfactory customer service.

Moreover, a useful agent should be able to identify and incorperate the ambiguities of user response during its conversation with the user for recommending products. What does a' dark' color refer to? What does 'better to be white' means? Agents need to be equipped with the capability to understand these soft constraints that cannot be directly captured through database filtering operations.

 To address these challenges, we have proposed a unique modular architecture that addresses these concerns, which will be explored in the next section.

## What the solution does

The agent follows a stateful `Intent -> Preference Store -> Ranker` pipeline:

1. **Understand the message.** A deterministic rule-first parser identifies buying,
   browsing, preference disclosure, boundary/no-preference, and intent-override
   messages. An optional DeepSeek parser handles ambiguous or paraphrased wording and
   must return strictly validated structured JSON.
2. **Maintain conversation state.** For each session, the agent stores the requested
   category, hard and soft constraints, safe aggregate profile tags, previously asked
   or declined attributes, and products already shown.
3. **Ask useful clarification questions.** When the request is broad, the agent asks
   for one high-value attribute such as material, color, budget, feature, or use case.
   It continues recommending products while gathering information, so the interaction
   remains useful on every turn.
4. **Retrieve candidates locally.** An in-memory SQLite FTS5 index searches product
   titles, categories, features, details, descriptions, stores, and other catalog
   text. Multiple lexical routes combine broad category retrieval with per-constraint
   AND/OR searches.
5. **Rerank and diversify.** Candidates are scored using category and constraint
   coverage, exact phrase matches, title overlap, price/range compatibility, profile
   relevance, rating, and popularity. A title-diversity pass prevents the Top 10 from
   being filled with near-duplicate products.
6. **Adapt exploration to conversation progress.** While the agent has very little
   evidence, it shows only its two strongest examples and keeps clarifying instead of
   prematurely returning ten weak guesses. Once enough preferences are known, or the
   early clarification window closes, it returns the full requested result count.

## How we built it

We began with the organizer's stateless BM25-style starter and iterated through state
management, structured clarification, multi-route retrieval, reranking,
non-repetition, override handling, title diversity, caching, and evidence-gated
recommendation warmup.

Experiments used a deterministic scenario-stratified development/holdout split. We
also created two frozen 100-session audit sets whose target products do not overlap
the 200 public targets. Diversity, warmup, retrieval, and ranking variants were
accepted only when they improved validation behavior without an unacceptable Hit-Rate
loss. Rejected experiments remain documented in `progress.md` so the selected result
does not hide negative findings.

The best accepted configuration is the deterministic default with
`DEEPSEEK_MODE=off`:

| Dataset | Sessions | Hit Rate@10 | MRR | MTTC | Efficiency | TechnicalScore |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Public | 200 | **0.995** | **0.836357** | **2.540** | **0.846** | **0.917607** |
| Generalization audit | 100 | **0.970** | **0.798806** | **2.900** | **0.810** | **0.886642** |
| Category-gap audit | 100 | **1.000** | **0.842440** | **2.600** | **0.840** | **0.920732** |

The two 100-target sets are participant-created robustness checks, not estimates of
the organizer's private leaderboard. Lower scores from rejected model and retrieval
experiments are retained in `progress.md`, not mixed into the accepted result above.

## How to reproduce the verified result

After completing the catalog download and checksum steps in `README.md`, run these
commands from the repository root. Explicit `DEEPSEEK_MODE=off` prevents an API key or
shell setting from changing the accepted configuration:

```bash
DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m unittest -v

DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m evaluator.local_evaluator \
  --output /tmp/techjam_public_results.json

DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m evaluator.local_evaluator \
  --dataset data/generalization_set.jsonl \
  --output /tmp/techjam_generalization_results.json

DEEPSEEK_MODE=off PYTHONHASHSEED=2 python3 -m evaluator.local_evaluator \
  --dataset data/category_gap_set.jsonl \
  --output /tmp/techjam_category_gap_results.json
```

The first command passes 25 tests. The three evaluator commands reproduce the table
above when using the published catalog checksum. Runtime varies by CPU and SQLite
build, so only the deterministic metrics are claimed.

## Development tools used

- **Python command-line environment** for implementation, evaluation, profiling, and
  reproducible experiments
- **Git and GitHub** for source control, branching, synchronization, and collaboration
- **Codex and Claude Code** as AI-assisted development and code-review tools, with a
  shared `progress.md` handoff document to preserve experiment context
- **Python `unittest` and `cProfile`** for regression testing and performance analysis
- The project is editor-agnostic and was evaluated through local scripts rather than
  requiring Colab or Jupyter notebooks

## APIs and models used

- **DeepSeek API — `deepseek-v4-flash`**, optionally used as a rule-first fallback for
  ambiguous or paraphrased intent parsing
- The API key is read only from the `DEEPSEEK_API_KEY` environment variable and is
  never stored in source code or exported conversation logs
- DeepSeek does not retrieve products or generate product identifiers. It only
  converts the current message and compact session context into validated intent and
  constraint fields; catalog search and ranking remain deterministic
- The recommended public evaluation path makes zero model calls and works without
  network access. Forced LLM evaluation scored below the deterministic configuration
  on the public and both disjoint audit sets, so calling the model on every turn was
  rejected; full rejected-run details remain in `progress.md`
- No OpenAI, Google Maps, or other external runtime API is required by the agent

## Libraries and frameworks used

The submission intentionally has **no third-party Python runtime dependencies**. It
uses the Python standard library, primarily:

- **`sqlite3` with FTS5** for in-memory full-text indexing and BM25 candidate retrieval
- **`dataclasses`** for structured intents, preferences, and cached ranking signals
- **`json`, `re`, and `urllib`** for structured parsing, deterministic rules, and the
  optional DeepSeek HTTPS client
- **`math` and standard collection utilities** for reranking and diversification
- **`unittest`** for the 25-test regression suite
- **`cProfile`** for response-time profiling

No PyTorch, TensorFlow, Hugging Face Transformers, scikit-learn, pandas, vector
database, or model download is required. This keeps startup, deployment, and offline
evaluation simple.

## Datasets and assets used

- **Amazon Reviews 2023**, published by McAuley Lab at UCSD
- The organizer-provided frozen **`Clothing_Shoes_and_Jewelry` catalog**, containing
  50,000 products and structured fields such as title, category, features,
  description, price, rating, store, and `parent_asin`
- **200 organizer-provided public development sessions** covering 40% Buying, 40%
  Browsing, 15% Intent Override, and 5% Boundary behavior
- **Anonymized aggregate user profiles** supplied by the challenge; raw user IDs,
  review text, timestamps, and raw purchase histories are not used
- **Two participant-created 100-session audit sets** generated deterministically from
  the frozen catalog using the public schema. Their target products are disjoint from
  the public targets and from each other; they are used only for generalization and
  category-coverage regression checks

The customer conversations are simulated from catalog-derived hidden intent cards;
Amazon Reviews 2023 does not contain these shopping conversations. The solution uses
text and structured metadata only—no product images, videos, private organizer data,
or manually reconstructed private labels.

Dataset attribution: <https://amazon-reviews-2023.github.io/>

## Challenges and lessons learned

The largest challenge was balancing early conversion against recommendation quality.
The evaluator ends a session as soon as the target first appears, so a lucky rank-9
guess on an under-informed first turn permanently records a weak reciprocal rank.
Showing two strong examples while asking a useful question produced better later
rankings without reducing public Hit Rate.

We also learned that adding more retrieval routes or calling an LLM more often does
not automatically improve the system. Forced DeepSeek parsing increased latency and
reduced MRR on canonical messages. Several broader retrieval and hand-tuned ranking
variants were also rejected when they failed validation. The most valuable
improvements came from careful state handling, deterministic ranking features,
measured exploration, and honest cross-set validation.

## What is next

Our next priorities are to test natural paraphrases separately from canonical
simulator messages, evaluate category-grouped folds, improve ambiguous Buying and
Boundary ranking without scenario-specific exceptions, and measure p50/p95 latency in
a clean Python 3.10+ submission environment. We would only add dense semantic
retrieval or a learned reranker if it improves generalization enough to justify the
additional dependencies and deployment risk.
