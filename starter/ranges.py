from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# ── Known attribute value sets (for catalog extraction) ──────────────────────

KNOWN_COLORS = frozenset({
    "black", "white", "blue", "red", "pink", "green", "brown", "gray", "grey",
    "purple", "yellow", "orange", "navy", "beige", "cream", "ivory", "tan",
    "gold", "silver", "teal", "coral", "burgundy", "maroon", "charcoal",
    "khaki", "olive", "lavender", "turquoise", "magenta", "rust",
})

KNOWN_MATERIALS = frozenset({
    "cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk",
    "rayon", "linen", "denim", "fleece", "cashmere", "suede", "velvet",
    "satin", "chiffon", "acrylic", "lycra", "flannel", "mesh", "canvas",
    "rubber", "latex", "hemp", "tweed",
})

KNOWN_SIZES = frozenset({
    "xs", "small", "medium", "large", "xl", "xxl", "2xl", "3xl", "4xl", "5xl",
    "one size", "petite", "plus", "tall",
})

KNOWN_STYLES = frozenset({
    "casual", "formal", "athletic", "sporty", "vintage", "bohemian", "classic",
    "modern", "slim", "relaxed", "oversized", "fitted", "loose", "tapered",
    "v-neck", "crew neck", "long sleeve", "short sleeve", "sleeveless",
    "button-down", "hooded", "zip-up",
})

KNOWN_USE_CASES = frozenset({
    "running", "hiking", "gym", "yoga", "golf", "tennis", "swimming",
    "work", "office", "outdoor", "indoor", "winter", "summer", "rain",
    "beach", "travel", "sleep", "lounge", "party", "wedding", "everyday",
})

# ── Color / material / style group mappings ──────────────────────────────────

DARK_COLORS = frozenset({
    "black", "navy", "charcoal", "dark grey", "dark gray", "dark brown",
    "dark blue", "dark green", "burgundy", "maroon",
})
LIGHT_COLORS = frozenset({
    "white", "cream", "ivory", "beige", "light grey", "light gray",
    "light blue", "light pink", "lavender", "tan",
})
WARM_COLORS = frozenset({
    "red", "orange", "yellow", "coral", "burgundy", "rust", "gold", "magenta",
})
COOL_COLORS = frozenset({
    "blue", "navy", "teal", "green", "purple", "turquoise", "lavender",
})
NEUTRAL_COLORS = frozenset({
    "black", "white", "grey", "gray", "beige", "cream", "navy", "brown",
    "tan", "khaki", "charcoal", "ivory", "olive",
})

COLOR_GROUPS: dict[str, frozenset[str]] = {
    "dark": DARK_COLORS,
    "light": LIGHT_COLORS,
    "warm": WARM_COLORS,
    "cool": COOL_COLORS,
    "neutral": NEUTRAL_COLORS,
}

NATURAL_MATERIALS = frozenset({
    "cotton", "wool", "silk", "linen", "leather", "hemp", "cashmere",
})
SYNTHETIC_MATERIALS = frozenset({
    "polyester", "nylon", "spandex", "acrylic", "rayon", "lycra", "latex",
})
WARM_MATERIALS = frozenset({
    "wool", "fleece", "flannel", "cashmere", "velvet",
})

MATERIAL_GROUPS: dict[str, frozenset[str]] = {
    "natural": NATURAL_MATERIALS,
    "synthetic": SYNTHETIC_MATERIALS,
    "warm": WARM_MATERIALS,
}

CASUAL_STYLES = frozenset({
    "casual", "relaxed", "everyday", "loose",
})
FORMAL_STYLES = frozenset({
    "formal", "classic", "fitted", "button-down",
})
ACTIVE_STYLES = frozenset({
    "athletic", "sporty", "fitted",
})

STYLE_GROUPS: dict[str, frozenset[str]] = {
    "casual": CASUAL_STYLES,
    "formal": FORMAL_STYLES,
    "active": ACTIVE_STYLES,
    "athletic": ACTIVE_STYLES,
    "sport": ACTIVE_STYLES,
}

BUDGET_KEYWORDS: dict[str, tuple[float, float]] = {
    "cheap": (0, 25),
    "affordable": (0, 35),
    "budget": (0, 30),
    "inexpensive": (0, 30),
    "mid-range": (25, 60),
    "moderate": (20, 50),
    "premium": (50, 120),
    "expensive": (60, 200),
    "luxury": (80, 200),
    "high-end": (60, 200),
}

PRICE_PATTERN = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")
UNDER_PATTERN = re.compile(r"(?:under|below|less than|max|maximum)\s*\$?\s*(\d+(?:\.\d+)?)", re.I)
OVER_PATTERN = re.compile(r"(?:over|above|more than|at least|minimum)\s*\$?\s*(\d+(?:\.\d+)?)", re.I)
RANGE_PATTERN = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*[-–to]+\s*\$?\s*(\d+(?:\.\d+)?)", re.I)

_COLOR_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in sorted(KNOWN_COLORS, key=len, reverse=True)) + r")\b", re.I)
_MATERIAL_RE = re.compile(r"\b(" + "|".join(re.escape(m) for m in sorted(KNOWN_MATERIALS, key=len, reverse=True)) + r")\b", re.I)


# ── Abstract range ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttributeRange(ABC):
    """A resolved set of concrete values for one preference attribute."""

    @abstractmethod
    def matches(self, product_value: str) -> float:
        """Score [0.0, 1.0] how well a product value fits this range."""

    @abstractmethod
    def breadth(self) -> float:
        """Fraction of the attribute universe this range covers (0=specific, 1=everything)."""

    @abstractmethod
    def narrowed_by(self, subset: object) -> AttributeRange:
        """Return a new range narrowed to the given subset."""


# ── Numerical range (budget, price) ──────────────────────────────────────────

@dataclass(frozen=True)
class NumericalRange(AttributeRange):
    """Range for numeric attributes: budget/price."""

    low: float
    high: float
    universe_low: float = 0.0
    universe_high: float = 200.0

    def matches(self, product_value: str) -> float:
        try:
            val = float(product_value)
        except (TypeError, ValueError):
            return 0.0
        if self.low <= val <= self.high:
            return 1.0
        # Smooth decay outside range
        span = max(self.high - self.low, 1.0)
        if val < self.low:
            return max(0.0, 1.0 - (self.low - val) / span)
        return max(0.0, 1.0 - (val - self.high) / span)

    def matches_price(self, price: float | None) -> float:
        if price is None:
            return 0.0
        return self.matches(str(price))

    def breadth(self) -> float:
        universe_span = max(self.universe_high - self.universe_low, 1.0)
        return min(1.0, (self.high - self.low) / universe_span)

    def narrowed_by(self, subset: tuple[float, float]) -> NumericalRange:
        lo, hi = subset
        return NumericalRange(
            low=max(self.low, lo),
            high=min(self.high, hi),
            universe_low=self.universe_low,
            universe_high=self.universe_high,
        )


# ── Ordinal range (color, material, style, etc.) ────────────────────────────

@dataclass(frozen=True)
class OrdinalRange(AttributeRange):
    """Range for categorical attributes: color, material, style, size, etc."""

    selected: frozenset[str]
    universe: frozenset[str] = frozenset()

    def matches(self, product_value: str) -> float:
        if not self.selected:
            return 0.0
        lowered = product_value.lower()
        for val in self.selected:
            if val in lowered:
                return 1.0
        return 0.0

    def breadth(self) -> float:
        if not self.universe:
            return 0.0
        return len(self.selected) / len(self.universe)

    def narrowed_by(self, subset: set[str]) -> OrdinalRange:
        return OrdinalRange(
            selected=self.selected & frozenset(subset),
            universe=self.universe,
        )


# ── Catalog registry ────────────────────────────────────────────────────────

@dataclass
class CatalogRegistryBuilder:
    """Single-pass accumulator: call observe(product) for each catalog row."""

    _prices: list[float] = field(default_factory=list)
    _colors: set[str] = field(default_factory=set)
    _materials: set[str] = field(default_factory=set)
    _brands: set[str] = field(default_factory=set)

    def observe(self, product: dict) -> None:
        price = product.get("price")
        if price is not None:
            try:
                self._prices.append(float(price))
            except (TypeError, ValueError):
                pass

        title = str(product.get("title") or "")
        features_text = " ".join(product.get("features") or [])
        details = product.get("details") or {}
        detail_color = str(details.get("Color") or details.get("color") or "")
        searchable = f"{title} {detail_color}"

        for m in _COLOR_RE.finditer(searchable):
            self._colors.add(m.group(1).lower())

        for m in _MATERIAL_RE.finditer(features_text):
            self._materials.add(m.group(1).lower())

        store = product.get("store")
        if store and str(store).strip():
            self._brands.add(str(store).strip())

    def build(self) -> CatalogRegistry:
        if self._prices:
            price_range = (min(self._prices), max(self._prices))
        else:
            price_range = (0.0, 200.0)
        return CatalogRegistry(
            price_range=price_range,
            colors=frozenset(self._colors),
            materials=frozenset(self._materials),
            brands=frozenset(self._brands),
        )


@dataclass(frozen=True)
class CatalogRegistry:
    """Frozen attribute universe extracted from the catalog."""

    price_range: tuple[float, float]
    colors: frozenset[str]
    materials: frozenset[str]
    brands: frozenset[str]

    def universe_for(self, attribute: str) -> frozenset[str] | tuple[float, float]:
        if attribute == "budget":
            return self.price_range
        if attribute == "color":
            return self.colors
        if attribute == "material":
            return self.materials
        if attribute == "brand":
            return self.brands
        return frozenset()


# ── determine_range — the LLM hook point ────────────────────────────────────

def determine_range(
    attribute: str,
    value: str,
    registry: CatalogRegistry,
) -> AttributeRange | None:
    """Translate a preference keyword/phrase into a concrete range.

    Returns None if no mapping can be determined — preference stays text-only
    and existing text-matching scoring applies.

    TODO: LLM hook — call LLM with (attribute, value, universe_values)
      returning {"type": "ordinal", "selected": [...]}
      or {"type": "numerical", "low": float, "high": float}
      Keep this rule-based version as fallback when LLM is unavailable.
    """
    return _determine_range_rule_based(attribute, value, registry)


def _determine_range_rule_based(
    attribute: str,
    value: str,
    registry: CatalogRegistry,
) -> AttributeRange | None:
    lowered = value.lower()

    if attribute == "budget":
        return _resolve_budget(lowered, registry)
    if attribute == "color":
        return _resolve_from_groups(lowered, COLOR_GROUPS, registry.colors)
    if attribute == "material":
        return _resolve_from_groups(lowered, MATERIAL_GROUPS, registry.materials)
    if attribute == "style":
        return _resolve_from_groups(lowered, STYLE_GROUPS, KNOWN_STYLES)
    return None


def _resolve_budget(lowered: str, registry: CatalogRegistry) -> NumericalRange | None:
    plo, phi = registry.price_range

    # Explicit range: "$30-$60"
    m = RANGE_PATTERN.search(lowered)
    if m:
        return NumericalRange(low=float(m.group(1)), high=float(m.group(2)),
                              universe_low=plo, universe_high=phi)
    # "under $50"
    m = UNDER_PATTERN.search(lowered)
    if m:
        return NumericalRange(low=plo, high=float(m.group(1)),
                              universe_low=plo, universe_high=phi)
    # "over $50"
    m = OVER_PATTERN.search(lowered)
    if m:
        return NumericalRange(low=float(m.group(1)), high=phi,
                              universe_low=plo, universe_high=phi)
    # Bare "$50"
    m = PRICE_PATTERN.search(lowered)
    if m:
        target = float(m.group(1))
        margin = max(target * 0.3, 10.0)
        return NumericalRange(low=max(plo, target - margin), high=target + margin,
                              universe_low=plo, universe_high=phi)
    # Keyword: "cheap", "premium", etc.
    for keyword, (lo, hi) in BUDGET_KEYWORDS.items():
        if keyword in lowered:
            return NumericalRange(low=lo, high=hi, universe_low=plo, universe_high=phi)
    return None


def _resolve_from_groups(
    lowered: str,
    groups: dict[str, frozenset[str]],
    universe: frozenset[str],
) -> OrdinalRange | None:
    # Check group keywords first: "dark colors", "natural fabric"
    for group_key, group_values in groups.items():
        if group_key in lowered:
            selected = group_values & universe if universe else group_values
            if selected:
                return OrdinalRange(selected=frozenset(selected), universe=universe)

    # Single value match: "blue", "cotton"
    for val in universe:
        if val in lowered:
            return OrdinalRange(selected=frozenset({val}), universe=universe)

    return None
