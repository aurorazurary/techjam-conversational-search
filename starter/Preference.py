from __future__ import annotations

from dataclasses import dataclass, field

from starter.Intent import Intent

# Map user_profile preference_tags to ALLOWED_ATTRIBUTES
TAG_TO_ATTRIBUTE: dict[str, str] = {
    "fit": "style",
    "comfort": "feature",
    "durability": "feature",
    "material": "material",
    "style": "style",
    "weather": "use_case",
    "warmth": "use_case",
    "performance": "feature",
    "brand": "brand",
    "use_case": "use_case",
    "color": "color",
    "budget": "budget",
    "size": "size",
}

# Default fallback order when preference_tags are exhausted
FALLBACK_ORDER = [
    "feature", "use_case", "style", "material", "color",
    "budget", "size", "brand", "category", "other",
]


@dataclass
class Preference:
    """Per-session state: accumulates constraints and drives questioning strategy."""

    category: str = ""
    constraints: dict[str, list[str]] = field(default_factory=dict)
    no_preference: set[str] = field(default_factory=set)
    asked_attributes: list[str] = field(default_factory=list)
    disclosed_values: set[str] = field(default_factory=set)
    override_active: bool = False
    user_profile_tags: list[str] = field(default_factory=list)

    def __init__(self, user_profile: dict) -> None:
        self.category = ""
        self.constraints = {}
        self.no_preference = set()
        self.asked_attributes = []
        self.disclosed_values = set()
        self.override_active = False
        self.user_profile_tags = list(user_profile.get("preference_tags") or [])

    def update(self, intent: Intent) -> None:
        """Incorporate a parsed Intent into session state."""
        # Handle override: clear old constraints, start fresh
        if intent.override_signal:
            self.constraints.clear()
            self.disclosed_values.clear()
            self.override_active = True

        # Handle no-preference signal
        if intent.no_preference_attr:
            self.no_preference.add(intent.no_preference_attr)

        # Set category from first message
        if intent.category_text and not self.category:
            self.category = intent.category_text

        # Accumulate constraints
        for constraint in intent.constraints:
            attr = constraint["attribute"]
            value = constraint["value"]
            if value not in self.disclosed_values:
                self.constraints.setdefault(attr, []).append(value)
                self.disclosed_values.add(value)

    def next_attribute_to_ask(self) -> str | None:
        """Pick the best attribute to ask about next.

        Returns None only when all attributes are exhausted.
        """
        already = set(self.asked_attributes) | self.no_preference

        # Phase 1: attributes derived from user_profile preference_tags
        tag_attrs: list[str] = []
        for tag in self.user_profile_tags:
            attr = TAG_TO_ATTRIBUTE.get(tag, "feature")
            if attr not in already and attr not in tag_attrs:
                tag_attrs.append(attr)

        for attr in tag_attrs:
            self.asked_attributes.append(attr)
            return attr

        # Phase 2: fallback order
        for attr in FALLBACK_ORDER:
            if attr not in already:
                self.asked_attributes.append(attr)
                return attr

        return None

    def to_search_terms(self) -> list[str]:
        """Flatten category + all constraint values into search terms."""
        terms: list[str] = []
        if self.category:
            terms.extend(self.category.split())
        for values in self.constraints.values():
            for value in values:
                terms.extend(value.split())
        return terms
