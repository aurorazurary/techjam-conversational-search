from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass

from starter.Preference import (
    PreferenceStore,
    HARDNESS_OVERRIDE,
    HARDNESS_DISCLOSED,
    _clean_value,
    _normalized,
)
from starter.intents import (
    Intent,
    BuyingIntent,
    BrowsingIntent,
    OverrideIntent,
    BoundaryIntent,
    InfoIntent,
)
from starter.ranges import (
    CatalogRegistry,
    NumericalRange,
    OrdinalRange,
    determine_range,
)

# ── Text processing ──────────────────────────────────────────────────────────

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
PRICE_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")

STOPWORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "but",
    "by", "can", "do", "does", "for", "from", "has", "have", "here", "i",
    "in", "is", "it", "key", "looking", "made", "me", "my", "need", "not",
    "of", "on", "or", "please", "some", "that", "the", "these", "this", "to",
    "want", "what", "with", "would", "you", "your",
}

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
    "range_match": 0.0,
}


def _terms(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def _fts_or(terms: list[str]) -> str:
    return " OR ".join(f'"{term}"' for term in dict.fromkeys(terms))


def _fts_and(terms: list[str]) -> str:
    return " AND ".join(f'"{term}"' for term in dict.fromkeys(terms))


# ── Cached product signals ───────────────────────────────────────────────────

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


# ── Ranker ───────────────────────────────────────────────────────────────────

class Ranker:
    """Applies intents to the PreferenceStore and ranks catalog products.

    Two responsibilities:
    1. apply_intent(store, intent) — mutates PreferenceStore based on Intent
    2. rank(store, top_k) — retrieves and ranks products using PreferenceStore
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        catalog_registry: CatalogRegistry | None = None,
        rerank_weights: dict[str, float] | None = None,
        diversity_strength: float = 6.0,
        expand_query_terms: bool = False,
    ) -> None:
        unknown = set(rerank_weights or {}) - set(DEFAULT_RERANK_WEIGHTS)
        if unknown:
            raise ValueError(f"unknown reranker weights: {', '.join(sorted(unknown))}")
        self.connection = connection
        self.catalog_registry = catalog_registry
        self.rerank_weights = {**DEFAULT_RERANK_WEIGHTS, **(rerank_weights or {})}
        self.diversity_strength = max(0.0, float(diversity_strength))
        self.expand_query_terms = bool(expand_query_terms)
        self._fetch_cache: dict[tuple[str, int], list[tuple]] = {}
        self._product_signal_cache: dict[str, ProductSignals] = {}

    # ── Intent → PreferenceStore ─────────────────────────────────────────

    def apply_intent(self, store: PreferenceStore, intent: Intent) -> None:
        """Map a parsed Intent into PreferenceStore mutations."""
        if isinstance(intent, OverrideIntent):
            store.seen_recommendations.clear()
            if store.initial_preference:
                store.remove_preference_by_value(store.initial_preference)
                store.initial_preference = ""
            for c in intent.constraints:
                store.add_preference(c["attribute"], c["value"], c.get("hardness", HARDNESS_OVERRIDE))

        elif isinstance(intent, BoundaryIntent):
            attr = intent.no_preference_attr
            if attr == "other":
                if store.broad_answers:
                    store.broad_exhausted = True
            elif attr:
                store.declined_attributes.add(attr)

        elif isinstance(intent, InfoIntent):
            added = False
            for c in intent.constraints:
                added = store.add_preference(c["attribute"], c["value"], c.get("hardness", HARDNESS_DISCLOSED)) or added
            if added:
                store.broad_answers += 1

        elif isinstance(intent, BuyingIntent):
            if intent.category_text and not store.category:
                store.category = _clean_value(intent.category_text)
            for c in intent.constraints:
                store.add_preference(c["attribute"], c["value"], c.get("hardness", HARDNESS_DISCLOSED))

        elif isinstance(intent, BrowsingIntent):
            if intent.category_text and not store.category:
                store.category = _clean_value(intent.category_text)
            if intent.constraints:
                c = intent.constraints[0]
                store.initial_preference = _clean_value(c["value"])
                store.add_preference(c["attribute"], c["value"], c.get("hardness", HARDNESS_DISCLOSED))

        # NoInfoIntent or unknown — no state change

        # Resolve ranges for any newly added preferences
        if self.catalog_registry:
            for pref in store.preferences:
                if pref.range is None:
                    pref.range = determine_range(pref.attribute, pref.value, self.catalog_registry)

    # ── Ranking pipeline ─────────────────────────────────────────────────

    def rank(self, store: PreferenceStore, top_k: int) -> list[dict]:
        """Retrieve, rerank, diversify, and return top-k recommendations."""
        candidates = self._candidate_rows(store)
        ranked = sorted(
            (
                (self._rerank_score(row, route_score, store), asin)
                for asin, (row, route_score) in candidates.items()
                if asin not in store.seen_recommendations
            ),
            reverse=True,
        )
        selected = self._select_diverse(ranked, candidates, top_k)
        store.seen_recommendations.update(selected)
        return [{"parent_asin": asin} for asin in selected]

    # ── FTS retrieval with caching ───────────────────────────────────────

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

    # ── Multi-route candidate generation ─────────────────────────────────

    def _candidate_rows(self, store: PreferenceStore) -> dict[str, tuple[tuple, float]]:
        category_terms = _terms(store.category)
        constraint_terms = [t for p in store.preferences for t in _terms(p.value)]
        profile_terms = [t for v in store.profile_tags for t in _terms(v)]
        all_terms = self._expand_terms(
            list(dict.fromkeys(category_terms + constraint_terms + profile_terms))
        )[:80]
        candidates: dict[str, tuple[tuple, float]] = {}

        def add(rows: list[tuple], route_weight: float) -> None:
            for rank_pos, row in enumerate(rows, start=1):
                asin = str(row[0])
                score = route_weight / (8.0 + rank_pos)
                existing = candidates.get(asin)
                if existing:
                    candidates[asin] = (existing[0], existing[1] + score)
                else:
                    candidates[asin] = (row, score)

        # Route 1: broad OR
        add(self._fetch(_fts_or(all_terms), 1200), 7.0)
        # Route 2: category AND
        if category_terms:
            add(self._fetch(_fts_and(category_terms[:6]), 350), 3.0)
        # Route 3: per-preference AND + OR
        for pref in store.preferences:
            terms = list(dict.fromkeys(_terms(pref.value)))
            if terms:
                add(self._fetch(_fts_and(terms[:12]), 180), 12.0)
                add(self._fetch(_fts_or(terms[:20]), 250), 4.0)
        # Route 4: range-expanded queries (ordinal ranges resolve to concrete values)
        for pref in store.preferences:
            if isinstance(pref.range, OrdinalRange) and pref.range.selected:
                range_terms = list(pref.range.selected)[:20]
                add(self._fetch(_fts_or(range_terms), 200), 3.0)
        return candidates

    # ── Product signal extraction (cached) ───────────────────────────────

    def _product_signals(self, row: tuple) -> ProductSignals:
        asin = str(row[0])
        cached = self._product_signal_cache.get(asin)
        if cached is not None:
            return cached
        _, title, categories, features, details, store_name, description, raw_price, raw_rating, raw_count, _ = row
        corpus = " ".join((title, categories, features, details, store_name, description))
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
        self._product_signal_cache[asin] = signals
        return signals

    # ── 10-feature reranker (hardness-weighted) ──────────────────────────

    @staticmethod
    def _price_score(constraint_value: str, price: float | None) -> float:
        if price is None:
            return 0.0
        match = PRICE_RE.search(constraint_value)
        if not match:
            return 0.0
        requested = float(match.group(1))
        lowered = constraint_value.lower()
        if any(w in lowered for w in ("under", "below", "less than", "maximum")):
            return 4.0 if price <= requested else -min(4.0, (price - requested) / max(requested, 1.0))
        relative_error = abs(price - requested) / max(requested, 1.0)
        return 5.0 * max(0.0, 1.0 - relative_error)

    def _rerank_features(self, row: tuple, route_score: float, store: PreferenceStore) -> dict[str, float]:
        signals = self._product_signals(row)
        features = {name: 0.0 for name in DEFAULT_RERANK_WEIGHTS}
        features["route_score"] = route_score

        cat_terms = set(_terms(store.category))
        if cat_terms:
            features["category_coverage"] = len(cat_terms & signals.category_terms) / len(cat_terms)
            norm_cat = _normalized(store.category)
            features["category_phrase"] = float(bool(norm_cat and norm_cat in signals.normalized_categories))

        for pref in store.preferences:
            terms = set(_terms(pref.value))
            if not terms:
                continue
            h = pref.hardness
            coverage = len(terms & signals.document_terms) / len(terms)
            title_cov = len(terms & signals.title_terms) / len(terms)
            features["constraint_coverage"] += h * coverage * coverage
            features["constraint_title_coverage"] += h * title_cov
            norm_c = _normalized(pref.value)
            features["constraint_phrase"] += h * float(bool(norm_c and norm_c in signals.normalized_corpus))
            features["price_compatibility"] += h * self._price_score(pref.value, signals.price)

        prof_terms = set(t for tag in store.profile_tags for t in _terms(tag))
        if prof_terms:
            features["profile_coverage"] = len(prof_terms & signals.document_terms) / len(prof_terms)

        # Range-based matching (supplements text matching for resolved ranges)
        for pref in store.preferences:
            if pref.range is None:
                continue
            h = pref.hardness
            if isinstance(pref.range, NumericalRange):
                features["range_match"] += h * pref.range.matches_price(signals.price)
            elif isinstance(pref.range, OrdinalRange):
                features["range_match"] += h * pref.range.matches(signals.normalized_corpus)

        features["rating_quality"] = max(0.0, signals.rating - 3.0)
        features["rating_popularity"] = min(12.0, math.log1p(max(0, signals.rating_count)))
        return features

    def _rerank_score(self, row: tuple, route_score: float, store: PreferenceStore) -> float:
        features = self._rerank_features(row, route_score, store)
        return sum(self.rerank_weights[n] * v for n, v in features.items())

    # ── Title diversity selection ────────────────────────────────────────

    def _select_diverse(
        self,
        ranked: list[tuple[float, str]],
        candidates: dict[str, tuple[tuple, float]],
        top_k: int,
    ) -> list[str]:
        if not ranked or self.diversity_strength <= 0.0:
            return [asin for _, asin in ranked[:top_k]]
        pool = ranked[:max(100, top_k * 10)]
        selected: list[str] = []
        selected_titles: list[frozenset[str]] = []
        while pool and len(selected) < top_k:
            best_idx = 0
            best_score = float("-inf")
            for idx, (base_score, asin) in enumerate(pool):
                title_terms = self._product_signals(candidates[asin][0]).title_terms
                sims = [
                    len(title_terms & prior) / max(1, len(title_terms | prior))
                    for prior in selected_titles
                ]
                div_score = base_score - self.diversity_strength * max(sims, default=0.0)
                if div_score > best_score:
                    best_idx = idx
                    best_score = div_score
            _, asin = pool.pop(best_idx)
            selected.append(asin)
            selected_titles.append(self._product_signals(candidates[asin][0]).title_terms)
        return selected
