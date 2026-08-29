from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from starter.intents import Intent
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
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.broad_question_limit = max(1, int(broad_question_limit))
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, PreferenceStore] = {}
        self._build_index()
        self.ranker = Ranker(
            self.connection,
            catalog_registry=self.catalog_registry,
            rerank_weights=rerank_weights,
            diversity_strength=diversity_strength,
            expand_query_terms=expand_query_terms,
        )

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
        intent = Intent.from_message(user_message, turn)
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
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
