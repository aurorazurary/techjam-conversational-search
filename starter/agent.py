from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


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


class Agent:
    """Offline conversational retrieval agent with stateful constraint reranking."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, SessionState] = {}
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
                batch.append(
                    (
                        str(product["parent_asin"]),
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
        try:
            return self.connection.execute(
                "SELECT parent_asin, title, categories, features, details, store, description, "
                "price, average_rating, rating_number, "
                "bm25(products, 0.0, 7.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0) "
                "FROM products WHERE products MATCH ? ORDER BY 11 LIMIT ?",
                (expression, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    def _candidate_rows(self, state: SessionState) -> dict[str, tuple[tuple, float]]:
        category_terms = _terms(state.category)
        constraint_terms = [term for value in state.constraints for term in _terms(value)]
        profile_terms = [term for value in state.profile_tags for term in _terms(value)]
        all_terms = list(dict.fromkeys(category_terms + constraint_terms + profile_terms))[:80]
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

    def _rerank_score(self, row: tuple, route_score: float, state: SessionState) -> float:
        _, title, categories, features, details, store, description, raw_price, raw_rating, raw_count, _ = row
        corpus = " ".join((title, categories, features, details, store, description))
        normalized_corpus = _normalized(corpus)
        document_terms = set(_terms(corpus))
        title_terms = set(_terms(title))
        category_document_terms = set(_terms(categories))
        score = route_score

        category_terms = set(_terms(state.category))
        if category_terms:
            category_coverage = len(category_terms & category_document_terms) / len(category_terms)
            score += 8.0 * category_coverage
            normalized_category = _normalized(state.category)
            if normalized_category and normalized_category in _normalized(categories):
                score += 5.0

        for constraint in state.constraints:
            terms = set(_terms(constraint))
            if not terms:
                continue
            coverage = len(terms & document_terms) / len(terms)
            title_coverage = len(terms & title_terms) / len(terms)
            score += 13.0 * coverage * coverage
            score += 5.0 * title_coverage
            normalized_constraint = _normalized(constraint)
            if normalized_constraint and normalized_constraint in normalized_corpus:
                score += 18.0
            try:
                price = float(raw_price) if raw_price else None
            except (TypeError, ValueError):
                price = None
            score += self._price_score(constraint, price)

        profile_terms = set(term for tag in state.profile_tags for term in _terms(tag))
        if profile_terms:
            score += 0.5 * len(profile_terms & document_terms) / len(profile_terms)

        try:
            rating = float(raw_rating) if raw_rating else 0.0
        except (TypeError, ValueError):
            rating = 0.0
        try:
            rating_count = int(float(raw_count)) if raw_count else 0
        except (TypeError, ValueError):
            rating_count = 0
        score += min(0.4, max(0.0, rating - 3.0) * 0.08)
        score += min(0.6, math.log1p(max(0, rating_count)) * 0.05)
        return score

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
        selected = [parent_asin for _, parent_asin in ranked[:top_k]]
        state.seen_recommendations.update(selected)
        return [{"parent_asin": parent_asin} for parent_asin in selected]

    def _next_question(self, state: SessionState) -> tuple[str, str]:
        if not state.broad_exhausted and state.broad_answers < 2:
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
        self._update_state(state, user_message)
        recommendations = self._recommend(state, top_k)
        message, ask_attribute = self._next_question(state)
        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
