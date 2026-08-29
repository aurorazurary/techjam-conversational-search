from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from starter.Intent_generator import IntentGenerator
from starter.Preference import PreferenceStore
from starter.Ranker import Ranker
from starter.ranges import CatalogRegistryBuilder


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


class Agent:
    """Conversational shopping agent.

    Orchestrates three concerns:
      Intent   (starter/intents/)    — parse user message into an action
      Preference (starter/Preference.py) — accumulated user state for ranking
      Ranker   (starter/Ranker.py)   — apply intents + rank catalog products
    """

    def __init__(
        self,
        catalog_path: str | Path = "data/catalog.jsonl",
        *,
        rerank_weights: dict[str, float] | None = None,
        diversity_strength: float = 6.0,
        broad_question_limit: int = 2,
        expand_query_terms: bool = False,
        intent_generator: IntentGenerator | None = None,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.broad_question_limit = max(1, int(broad_question_limit))
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, PreferenceStore] = {}
        self.intent_generator = intent_generator or IntentGenerator.from_env()
        self._build_index()
        self.ranker = Ranker(
            self.connection,
            catalog_registry=self.catalog_registry,
            rerank_weights=rerank_weights,
            diversity_strength=diversity_strength,
            expand_query_terms=expand_query_terms,
        )

    @property
    def diversity_strength(self) -> float:
        """Compatibility proxy for the ranker's diversity control."""
        return self.ranker.diversity_strength

    @diversity_strength.setter
    def diversity_strength(self, value: float) -> None:
        self.ranker.diversity_strength = max(0.0, float(value))

    @property
    def expand_query_terms(self) -> bool:
        """Compatibility proxy for opt-in lexical expansion."""
        return self.ranker.expand_query_terms

    @expand_query_terms.setter
    def expand_query_terms(self, value: bool) -> None:
        self.ranker.expand_query_terms = bool(value)

    def _fetch(self, expression: str, limit: int) -> list[tuple]:
        """Compatibility proxy for cached FTS retrieval."""
        return self.ranker._fetch(expression, limit)

    def _expand_terms(self, terms: list[str]) -> list[str]:
        """Compatibility proxy for the ranker's query expansion."""
        return self.ranker._expand_terms(terms)

    def _build_index(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "price UNINDEXED, average_rating UNINDEXED, rating_number UNINDEXED, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        registry_builder = CatalogRegistryBuilder()
        batch: list[tuple[str, ...]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                registry_builder.observe(product)
                batch.append((
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
                ))
                if len(batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()
        self.catalog_registry = registry_builder.build()

    def reset(self, session_id: str, user_profile: dict) -> None:
        tags = user_profile.get("preference_tags") or []
        self._sessions[session_id] = PreferenceStore(
            profile_tags=[str(tag) for tag in tags if str(tag).strip()]
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
        pref = self._sessions[session_id]

        # Parse → update preference → rank → ask
        intent = self.intent_generator.generate(user_message, turn, pref)
        self.ranker.apply_intent(pref, intent)
        recommendations = self.ranker.rank(pref, top_k)

        if turn < 10:
            message, ask_attribute = pref.next_question(self.broad_question_limit)
            message = f"Here are some options. {message}"
        else:
            message = "Based on everything you've told me, here are my top recommendations."
            ask_attribute = None

        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": {
                "prompt_tokens": intent.prompt_tokens,
                "completion_tokens": intent.completion_tokens,
            },
        }
