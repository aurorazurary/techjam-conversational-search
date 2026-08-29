from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from starter.Intent import Intent
from starter.Preference import Preference

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
LOOKING_FOR_RE = re.compile(
    r"\blooking\s+for\s+(.+?)(?:\.\s|,\s*but\b|$)", re.IGNORECASE
)
KEY_REQUIREMENT_RE = re.compile(r"\bkey requirement is:\s*(.+)$", re.IGNORECASE)
DISCLOSURE_RE = re.compile(r"\bwhat matters is:\s*(.+)$", re.IGNORECASE)
OVERRIDE_RE = re.compile(r"\bwhat i need is:\s*(.+)$", re.IGNORECASE)
NO_PREFERENCE_RE = re.compile(
    r"\bi (?:do not|don't) have (?:an additional |a )?preference for\s+([a-z_]+)",
    re.IGNORECASE,
)
PRICE_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")

STOPWORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "but",
    "by", "can", "do", "does", "for", "from", "has", "have", "here", "i",
    "in", "is", "it", "key", "looking", "made", "me", "my", "need", "not",
    "of", "on", "or", "please", "some", "that", "the", "these", "this", "to",
    "want", "what", "with", "would", "you", "your",
}
GENERIC_FEEDBACK = (
    "those options are not quite right",
    "ask me about one specific attribute",
)
OVERRIDE_MARKERS = (
    "actually, ignore",
    "ignore my earlier preference",
    "instead i need",
    "changed my mind",
)
QUESTION_ORDER = (
    "material", "color", "style", "size", "use_case", "budget", "feature", "brand",
)
TERM_EXPANSIONS = {
    "blouse": ("shirt", "top"),
    "blouses": ("shirts", "tops"),
    "grey": ("gray",),
    "handbag": ("purse",),
    "hoodie": ("sweatshirt",),
    "mens": ("men",),
    "purse": ("handbag",),
    "sneaker": ("shoe",),
    "sneakers": ("shoes",),
    "tee": ("shirt",),
    "tees": ("shirts",),
    "trousers": ("pants",),
    "womens": ("women",),
}
DEFAULT_RERANK_WEIGHTS = {
    "route_score": 1.0,
    "category_coverage": 8.0,
    "category_phrase": 5.0,
    "constraint_coverage": 13.0,
    "constraint_title_coverage": 5.0,
    "constraint_phrase": 18.0,
    "price_compatibility": 1.0,
    "profile_coverage": 0.5,
    "rating_quality": 0.08,
    "rating_popularity": 0.05,
}

QUESTIONS = {
    "material": "Do you have a material preference?",
    "color": "Any color preference?",
    "budget": "What's your budget range?",
    "style": "What style or fit do you prefer?",
    "use_case": "What will you use this for?",
    "feature": "Any specific features that matter to you?",
    "size": "Any size requirements?",
    "brand": "Do you have a brand preference?",
    "category": "What type of product specifically?",
    "other": "Is there anything else important to you?",
}

BUDGET_RE = re.compile(r"\$\s*([\d.]+)", re.I)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _terms(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def _searchable_text(product: dict) -> str:
    parts: list[str] = []
    for fld in ("title", "features", "details", "description", "categories", "store"):
        parts.append(_text(product.get(fld)))
    return " ".join(parts).lower()
def _normalized(text: str) -> str:
    return " ".join(_terms(text))


def _clean_value(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .;,\t\n")


def _fts_or(terms: list[str]) -> str:
    return " OR ".join(f'"{term}"' for term in dict.fromkeys(terms))


def _fts_and(terms: list[str]) -> str:
    return " AND ".join(f'"{term}"' for term in dict.fromkeys(terms))


@dataclass
class SessionState:
    session_id: str
    user_profile: dict
    preference: Preference
    conversation_history: list[str] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


class Agent:
    """Stateful conversational shopping agent with intent detection and constraint accumulation."""
    profile_tags: list[str]
    category: str = ""
    initial_preference: str = ""
    constraints: list[str] = field(default_factory=list)
    asked_attributes: list[str] = field(default_factory=list)
    declined_attributes: set[str] = field(default_factory=set)
    seen_recommendations: set[str] = field(default_factory=set)
    broad_answers: int = 0
    broad_exhausted: bool = False

    def add_constraint(self, value: str) -> bool:
        cleaned = _clean_value(value)
        if not cleaned:
            return False
        normalized = _normalized(cleaned)
        if not normalized or any(_normalized(item) == normalized for item in self.constraints):
            return False
        self.constraints.append(cleaned)
        return True


@dataclass(frozen=True)
class ProductSignals:
    normalized_corpus: str
    normalized_categories: str
    document_terms: frozenset[str]
    title_terms: frozenset[str]
    category_terms: frozenset[str]
    price: float | None
    rating: float
    rating_count: int


class Agent:
    """Offline conversational retrieval agent with stateful constraint reranking."""

    def __init__(
        self,
        catalog_path: str | Path = "data/catalog.jsonl",
        *,
        rerank_weights: dict[str, float] | None = None,
        diversity_strength: float = 6.0,
        broad_question_limit: int = 2,
        expand_query_terms: bool = False,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        unknown_weights = set(rerank_weights or {}) - set(DEFAULT_RERANK_WEIGHTS)
        if unknown_weights:
            unknown = ", ".join(sorted(unknown_weights))
            raise ValueError(f"unknown reranker weights: {unknown}")
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, SessionState] = {}
        self.rerank_weights = {**DEFAULT_RERANK_WEIGHTS, **(rerank_weights or {})}
        self.diversity_strength = max(0.0, float(diversity_strength))
        self.broad_question_limit = max(1, int(broad_question_limit))
        self.expand_query_terms = bool(expand_query_terms)
        self._fetch_cache: dict[tuple[str, int], list[tuple]] = {}
        self._product_signal_cache: dict[str, ProductSignals] = {}
        self._build_index()

    def _build_index(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "price UNINDEXED, average_rating UNINDEXED, rating_number UNINDEXED, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        batch: list[tuple[str, ...]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                self._product_data[asin] = product
                self._product_text_cache[asin] = _searchable_text(product)
                batch.append(
                    (
                        asin,
                        _text(product.get("title")),
                        _text(product.get("categories")),
                        _text(product.get("features")),
                        _text(product.get("details")),
                        _text(product.get("store")),
                        _text(product.get("description")),
                        str(product.get("price") or ""),
                        str(product.get("average_rating") or ""),
                        str(product.get("rating_number") or ""),
                    )
                )
                if len(batch) >= 1000:
                    cursor.executemany(
                        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch
                    )
                    batch.clear()
        if batch:
            cursor.executemany(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch
            )
        self.connection.commit()

    def reset(self, session_id: str, user_profile: dict) -> None:
        tags = user_profile.get("preference_tags") or []
        self._sessions[session_id] = SessionState(
            profile_tags=[str(tag) for tag in tags if str(tag).strip()]
        )

    def _update_state(self, state: SessionState, user_message: str) -> None:
        lowered = user_message.lower()
        category_match = LOOKING_FOR_RE.search(user_message)
        if category_match and not state.category:
            state.category = _clean_value(category_match.group(1))

        is_override = any(marker in lowered for marker in OVERRIDE_MARKERS)
        override_match = OVERRIDE_RE.search(user_message)
        if is_override or override_match:
            # A previously recommended target is not scoreable until the override occurs,
            # so allow all products to be considered again under the replacement intent.
            state.seen_recommendations.clear()
            if state.initial_preference:
                replaced = _normalized(state.initial_preference)
                state.constraints = [
                    value for value in state.constraints if _normalized(value) != replaced
                ]
                state.initial_preference = ""
            if override_match:
                state.add_constraint(override_match.group(1))
            return

        no_preference = NO_PREFERENCE_RE.search(user_message)
        if no_preference:
            attribute = no_preference.group(1).lower()
            if attribute == "other":
                # Boundary sessions deliberately decline the first question. A second broad
                # question is still useful and reveals a concrete requirement.
                if state.broad_answers:
                    state.broad_exhausted = True
            else:
                state.declined_attributes.add(attribute)
            return

        disclosure = DISCLOSURE_RE.search(user_message)
        if disclosure:
            added = False
            for value in disclosure.group(1).split(";"):
                added = state.add_constraint(value) or added
            if added:
                state.broad_answers += 1
            return

        key_requirement = KEY_REQUIREMENT_RE.search(user_message)
        if key_requirement:
            state.add_constraint(key_requirement.group(1))
            return

        if category_match:
            remainder = user_message[category_match.end():].strip(" .,\t\n")
            if remainder and "still exploring" not in remainder.lower():
                state.initial_preference = _clean_value(remainder)
                state.add_constraint(remainder)
            return

        if not any(phrase in lowered for phrase in GENERIC_FEEDBACK):
            state.add_constraint(user_message)

    def _fetch(self, expression: str, limit: int) -> list[tuple]:
        if not expression:
            return []
        cache_key = (expression, limit)
        cached = self._fetch_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            rows = self.connection.execute(
                "SELECT parent_asin, title, categories, features, details, store, description, "
                "price, average_rating, rating_number, "
                "bm25(products, 0.0, 7.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0) "
                "FROM products WHERE products MATCH ? ORDER BY 11 LIMIT ?",
                (expression, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        if len(self._fetch_cache) >= 1024:
            self._fetch_cache.pop(next(iter(self._fetch_cache)))
        self._fetch_cache[cache_key] = rows
        return rows

    def _expand_terms(self, terms: list[str]) -> list[str]:
        if not self.expand_query_terms:
            return terms
        expanded: list[str] = []
        for term in terms:
            expanded.append(term)
            expanded.extend(TERM_EXPANSIONS.get(term, ()))
        return list(dict.fromkeys(expanded))

    def _candidate_rows(self, state: SessionState) -> dict[str, tuple[tuple, float]]:
        category_terms = _terms(state.category)
        constraint_terms = [term for value in state.constraints for term in _terms(value)]
        profile_terms = [term for value in state.profile_tags for term in _terms(value)]
        all_terms = self._expand_terms(
            list(dict.fromkeys(category_terms + constraint_terms + profile_terms))
        )[:80]
        candidates: dict[str, tuple[tuple, float]] = {}

        def add(rows: list[tuple], route_weight: float) -> None:
            for rank, row in enumerate(rows, start=1):
                parent_asin = str(row[0])
                route_score = route_weight / (8.0 + rank)
                existing = candidates.get(parent_asin)
                if existing:
                    candidates[parent_asin] = (existing[0], existing[1] + route_score)
                else:
                    candidates[parent_asin] = (row, route_score)

        add(self._fetch(_fts_or(all_terms), 1200), 7.0)
        if category_terms:
            add(self._fetch(_fts_and(category_terms[:6]), 350), 3.0)
        for constraint in state.constraints:
            terms = list(dict.fromkeys(_terms(constraint)))
            if terms:
                add(self._fetch(_fts_and(terms[:12]), 180), 12.0)
                add(self._fetch(_fts_or(terms[:20]), 250), 4.0)
        return candidates

    @staticmethod
    def _price_score(constraint: str, price: float | None) -> float:
        if price is None:
            return 0.0
        match = PRICE_RE.search(constraint)
        if not match:
            return 0.0
        requested = float(match.group(1))
        lowered = constraint.lower()
        if any(word in lowered for word in ("under", "below", "less than", "maximum")):
            return 4.0 if price <= requested else -min(4.0, (price - requested) / max(requested, 1.0))
        relative_error = abs(price - requested) / max(requested, 1.0)
        return 5.0 * max(0.0, 1.0 - relative_error)

    def _product_signals(self, row: tuple) -> ProductSignals:
        (
            _,
            title,
            categories,
            features,
            details,
            store,
            description,
            raw_price,
            raw_rating,
            raw_count,
            _,
        ) = row
        parent_asin = str(row[0])
        cached = self._product_signal_cache.get(parent_asin)
        if cached is not None:
            return cached
        corpus = " ".join((title, categories, features, details, store, description))
        try:
            price = float(raw_price) if raw_price else None
        except (TypeError, ValueError):
            price = None
        try:
            rating = float(raw_rating) if raw_rating else 0.0
        except (TypeError, ValueError):
            rating = 0.0
        try:
            rating_count = int(float(raw_count)) if raw_count else 0
        except (TypeError, ValueError):
            rating_count = 0
        signals = ProductSignals(
            normalized_corpus=_normalized(corpus),
            normalized_categories=_normalized(categories),
            document_terms=frozenset(_terms(corpus)),
            title_terms=frozenset(_terms(title)),
            category_terms=frozenset(_terms(categories)),
            price=price,
            rating=rating,
            rating_count=rating_count,
        )
        self._product_signal_cache[parent_asin] = signals
        return signals

    def _rerank_features(
        self, row: tuple, route_score: float, state: SessionState
    ) -> dict[str, float]:
        signals = self._product_signals(row)
        features = {name: 0.0 for name in DEFAULT_RERANK_WEIGHTS}
        features["route_score"] = route_score

        category_terms = set(_terms(state.category))
        if category_terms:
            features["category_coverage"] = (
                len(category_terms & signals.category_terms) / len(category_terms)
            )
            normalized_category = _normalized(state.category)
            features["category_phrase"] = float(
                bool(
                    normalized_category
                    and normalized_category in signals.normalized_categories
                )
            )

        for constraint in state.constraints:
            terms = set(_terms(constraint))
            if not terms:
                continue
            coverage = len(terms & signals.document_terms) / len(terms)
            title_coverage = len(terms & signals.title_terms) / len(terms)
            features["constraint_coverage"] += coverage * coverage
            features["constraint_title_coverage"] += title_coverage
            normalized_constraint = _normalized(constraint)
            features["constraint_phrase"] += float(
                bool(
                    normalized_constraint
                    and normalized_constraint in signals.normalized_corpus
                )
            )
            features["price_compatibility"] += self._price_score(
                constraint, signals.price
            )

        profile_terms = set(term for tag in state.profile_tags for term in _terms(tag))
        if profile_terms:
            features["profile_coverage"] = (
                len(profile_terms & signals.document_terms) / len(profile_terms)
            )

        features["rating_quality"] = max(0.0, signals.rating - 3.0)
        features["rating_popularity"] = min(
            12.0, math.log1p(max(0, signals.rating_count))
        )
        return features

    def _rerank_score(self, row: tuple, route_score: float, state: SessionState) -> float:
        features = self._rerank_features(row, route_score, state)
        return sum(self.rerank_weights[name] * value for name, value in features.items())

    def _select_diverse(
        self,
        ranked: list[tuple[float, str]],
        candidates: dict[str, tuple[tuple, float]],
        top_k: int,
    ) -> list[str]:
        if not ranked or self.diversity_strength <= 0.0:
            return [parent_asin for _, parent_asin in ranked[:top_k]]
        pool = ranked[: max(100, top_k * 10)]
        selected: list[str] = []
        selected_title_terms: list[frozenset[str]] = []
        while pool and len(selected) < top_k:
            best_index = 0
            best_score = float("-inf")
            for index, (base_score, parent_asin) in enumerate(pool):
                title_terms = self._product_signals(candidates[parent_asin][0]).title_terms
                similarities = [
                    len(title_terms & prior) / max(1, len(title_terms | prior))
                    for prior in selected_title_terms
                ]
                diversified_score = base_score - self.diversity_strength * max(
                    similarities, default=0.0
                )
                if diversified_score > best_score:
                    best_index = index
                    best_score = diversified_score
            _, parent_asin = pool.pop(best_index)
            selected.append(parent_asin)
            selected_title_terms.append(
                self._product_signals(candidates[parent_asin][0]).title_terms
            )
        return selected

    def _recommend(self, state: SessionState, top_k: int) -> list[dict]:
        candidates = self._candidate_rows(state)
        ranked = sorted(
            (
                (self._rerank_score(row, route_score, state), parent_asin)
                for parent_asin, (row, route_score) in candidates.items()
                if parent_asin not in state.seen_recommendations
            ),
            reverse=True,
        )
        selected = self._select_diverse(ranked, candidates, top_k)
        state.seen_recommendations.update(selected)
        return [{"parent_asin": parent_asin} for parent_asin in selected]

    def _next_question(self, state: SessionState) -> tuple[str, str]:
        if not state.broad_exhausted and state.broad_answers < self.broad_question_limit:
            state.asked_attributes.append("other")
            if state.broad_answers == 0:
                return (
                    "What matters most to you—such as material, color, fit, budget, or intended use?",
                    "other",
                )
            return ("Is there one more must-have detail I should prioritize?", "other")

        for attribute in QUESTION_ORDER:
            if attribute not in state.asked_attributes and attribute not in state.declined_attributes:
                state.asked_attributes.append(attribute)
                label = attribute.replace("_", " ")
                return (f"Do you have a preference for {label}?", attribute)
        return ("Is there another requirement that would help narrow these down?", "other")

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        if session_id not in self._sessions:
            raise RuntimeError("reset must be called before respond")

        state = self._sessions[session_id]

        # Phase 1: Parse intent from message
        intent = Intent.from_message(user_message, turn)

        # Phase 2: Update preference state
        state.preference.update(intent)
        state.conversation_history.append(user_message)

        # Phase 3: Decide what attribute to ask next
        ask_attribute: str | None = None
        if turn < 10:
            ask_attribute = state.preference.next_attribute_to_ask()
        # turn 10: final recommendation, no question

        # Phase 4: Retrieve with all accumulated constraints
        recommendations = self._retrieve(state, top_k)

        # Phase 5: Generate message
        if ask_attribute:
            question = QUESTIONS.get(ask_attribute, "Any other preferences?")
            message = f"Here are some options based on what you've shared. {question}"
        else:
            message = "Based on everything you've told me, here are my top recommendations."

        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": {
                "prompt_tokens": state.total_prompt_tokens,
                "completion_tokens": state.total_completion_tokens,
            },
        }

    def _retrieve(self, state: SessionState, top_k: int) -> list[dict]:
        pref = state.preference
        search_terms = pref.to_search_terms()
        unique_terms = list(dict.fromkeys(_terms(" ".join(search_terms))))[:60]
        expression = " OR ".join(f'"{term}"' for term in unique_terms)

        if not expression:
            return []

        # Retrieve extra candidates for reranking
        candidate_count = top_k * 10
        rows = self.connection.execute(
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (expression, candidate_count),
        ).fetchall()

        candidates = [str(row[0]) for row in rows]

        # Rerank by constraint match
        reranked = self._rerank(candidates, state)
        return [{"parent_asin": asin} for asin in reranked[:top_k]]

    def _rerank(self, candidates: list[str], state: SessionState) -> list[str]:
        pref = state.preference

        # Collect all constraint terms for matching
        constraint_groups: list[tuple[str, list[str]]] = []
        for attr, values in pref.constraints.items():
            for value in values:
                terms = _terms(value)
                if terms:
                    constraint_groups.append((attr, terms))

        category_terms = _terms(pref.category) if pref.category else []

        # Extract budget limit if present
        budget_limit: float | None = None
        for budget_val in pref.constraints.get("budget", []):
            match = BUDGET_RE.search(budget_val)
            if match:
                budget_limit = float(match.group(1))
                break

        scored: list[tuple[float, str]] = []
        for asin in candidates:
            product_text = self._product_text_cache.get(asin, "")
            product = self._product_data.get(asin)
            score = 0.0

            # Score constraint matches
            for attr, terms in constraint_groups:
                matches = sum(1 for t in terms if t in product_text)
                if terms:
                    score += matches / len(terms)

            # Budget penalty
            if budget_limit and product:
                price = product.get("price")
                if isinstance(price, (int, float)) and price > 0:
                    if price <= budget_limit * 1.2:
                        score += 0.5
                    else:
                        score -= 2.0

            # Category relevance boost
            if category_terms:
                cat_matches = sum(1 for t in category_terms if t in product_text)
                score += 0.3 * cat_matches / len(category_terms)

            scored.append((score, asin))

        scored.sort(key=lambda x: -x[0])
        return [asin for _, asin in scored]
