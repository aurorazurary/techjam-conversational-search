from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from starter.Intent import Intent
from starter.Preference import Preference

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
    "don", "t", "do", "have", "what", "matters", "preference", "not", "right",
    "yet", "ask", "about", "one", "specific", "attribute", "those", "options",
    "quite",
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

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, SessionState] = {}
        self._product_data: dict[str, dict] = {}
        self._product_text_cache: dict[str, str] = {}
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
                    )
                )
                if len(batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()

    def reset(self, session_id: str, user_profile: dict) -> None:
        self._sessions[session_id] = SessionState(
            session_id=session_id,
            user_profile=user_profile,
            preference=Preference(user_profile),
        )

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
