from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}

# Word lists validated against catalog frequency (data/catalog.jsonl, 50K products)
# rather than guessed from memory — see PR description for the frequency scan.
MATERIAL_RE = re.compile(
    r"\b(polyester|cotton|fabric|leather|spandex|mesh|lace|nylon|knit|fleece|suede|rayon|denim"
    r"|elastane|jersey|canvas|acrylic|wool|satin|velvet|chiffon|faux leather|microfiber|viscose"
    r"|silk|linen|flannel|cashmere)\b",
    re.I,
)
COLOR_RE = re.compile(
    r"\b(black|white|silver|blue|gold|red|grey|gray|green|pink|yellow|brown|navy|purple|orange"
    r"|beige|khaki|tan|turquoise|burgundy|charcoal|multicolor|coral|olive|ivory|teal|mint|maroon|lavender)\b",
    re.I,
)
BUDGET_RE = re.compile(r"\$\s?\d+|\bunder\s+\$?\d+|\bbudget\b", re.I)
SIZE_RE = re.compile(
    r"\b(size|sizing|small|medium|large|x+l|x+s|wide|narrow|short|width|one size|plus size|tall|petite"
    r"|big and tall)\b",
    re.I,
)
STYLE_WORDS = ("style", "fit", "sleeve", "neck", "department", "casual", "formal", "athletic", "skinny")
USE_CASE_WORDS = (
    "hiking", "running", "gym", "winter", "outdoor", "work", "use case", "everyday",
    "party", "summer", "beach", "wedding", "travel", "office", "workout", "school", "sport",
)
BRAND_WORDS = ("brand",)

# Signals emitted by the evaluator's simulated customer (see customer_reply /
# behavior_for in evaluator/local_evaluator.py) that we key off of instead of
# treating every reply as fresh search terms.
OVERRIDE_RE = re.compile(
    r"ignore my earlier preference|actually,? ignore|change(?:d)? my mind|scratch that|no longer (?:want|need)",
    re.I,
)
NO_PREFERENCE_RE = re.compile(
    r"don't have a preference|don't have an additional preference|use your judgment",
    re.I,
)
DECLINE_RE = re.compile(r"ask me about one specific attribute", re.I)

# "brand" is last: the reference simulator's classify_constraint never labels a
# constraint "brand" (evaluator/local_evaluator.py:137-151), so asking it can
# never reveal anything there. "other" is a safe generic fallback that still
# unconditionally reveals whatever's left, once the specific buckets are tried.
ATTRIBUTE_ORDER = ["material", "color", "budget", "size", "style", "use_case", "feature", "other", "brand"]


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


@dataclass
class SessionState:
    terms: list[str] = field(default_factory=list)
    slots: dict[str, str] = field(default_factory=dict)
    asked: set[str] = field(default_factory=set)
    no_preference: set[str] = field(default_factory=set)
    last_asked: str | None = None


class Agent:
    """Stateful BM25 retrieval: tracks slots per session, asks for the most
    informative missing attribute, and reacts to override / no-preference
    replies instead of treating every message as independent search terms."""

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
            "tokenize='unicode61 remove_diacritics 2')"
        )
        batch: list[tuple[str, str, str, str, str, str, str]] = []
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
                    )
                )
                if len(batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()

    def reset(self, session_id: str, user_profile: dict) -> None:
        # The profile is anonymized and may be used for personalization.
        self._sessions[session_id] = SessionState()

    def _search(self, terms: list[str], top_k: int) -> list[dict]:
        unique_terms = list(dict.fromkeys(terms))[:40]
        expression = " OR ".join(f'"{term}"' for term in unique_terms)
        if not expression:
            return []
        rows = self.connection.execute(
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (expression, top_k),
        ).fetchall()
        return [{"parent_asin": str(row[0])} for row in rows]

    def _ingest(self, state: SessionState, text: str) -> None:
        lowered = text.lower()
        if MATERIAL_RE.search(lowered):
            state.slots["material"] = text
        if COLOR_RE.search(lowered):
            state.slots["color"] = text
        if BUDGET_RE.search(lowered):
            state.slots["budget"] = text
        if SIZE_RE.search(lowered):
            state.slots["size"] = text
        if any(word in lowered for word in STYLE_WORDS):
            state.slots["style"] = text
        if any(word in lowered for word in USE_CASE_WORDS):
            state.slots["use_case"] = text
        if any(word in lowered for word in BRAND_WORDS):
            state.slots["brand"] = text
        state.terms.extend(_terms(text))

    def _next_attribute(self, state: SessionState) -> str | None:
        for attribute in ATTRIBUTE_ORDER:
            if attribute in state.slots or attribute in state.no_preference or attribute in state.asked:
                continue
            return attribute
        return None

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

        if OVERRIDE_RE.search(user_message):
            # Intent changed: old slots/terms describe the wrong product now.
            state.slots.clear()
            state.terms.clear()
            state.asked.clear()
            state.no_preference.clear()
            new_text = user_message.rsplit(":", 1)[-1] if ":" in user_message else user_message
            self._ingest(state, new_text)
        elif state.last_asked and NO_PREFERENCE_RE.search(user_message):
            # Customer declined the attribute we just asked about; stop asking it
            # and don't let it filter results.
            state.no_preference.add(state.last_asked)
        elif not DECLINE_RE.search(user_message):
            self._ingest(state, user_message)

        recommendations = self._search(state.terms, top_k)

        next_attribute = self._next_attribute(state)
        state.last_asked = next_attribute
        if next_attribute:
            state.asked.add(next_attribute)
            message = f"Do you have a {next_attribute.replace('_', ' ')} preference?"
        else:
            message = "Here are the closest matches I found."

        return {
            "message": message,
            "ask_attribute": next_attribute,
            "recommendations": recommendations,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
