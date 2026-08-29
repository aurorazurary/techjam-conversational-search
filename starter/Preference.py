from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starter.ranges import AttributeRange

QUESTION_ORDER = (
    "material", "color", "style", "size", "use_case", "budget", "feature", "brand",
)

_CLEAN_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "but",
    "by", "can", "do", "does", "for", "from", "has", "have", "here", "i",
    "in", "is", "it", "key", "looking", "made", "me", "my", "need", "not",
    "of", "on", "or", "please", "some", "that", "the", "these", "this", "to",
    "want", "what", "with", "would", "you", "your",
}


def _clean_value(text: str) -> str:
    return _CLEAN_RE.sub(" ", text).strip(" .;,\t\n")


def _normalized(text: str) -> str:
    return " ".join(
        t.lower() for t in _TOKEN_RE.findall(text)
        if len(t) > 1 and t.lower() not in _STOPWORDS
    )


# ── Hardness constants ───────────────────────────────────────────────────────

HARDNESS_HARD = 1.0
HARDNESS_REQUIREMENT = 0.9
HARDNESS_OVERRIDE = 1.0
HARDNESS_DISCLOSED = 0.6
HARDNESS_PROFILE = 0.3


@dataclass
class Preference:
    """A single user preference — one constraint with a degree of importance.

    hardness controls how strongly this preference affects ranking:
      1.0  = hard requirement (category, override)
      0.9  = key requirement explicitly stated
      0.6  = disclosed via conversation ("what matters is...")
      0.3  = inferred from user profile tags

    TODO: hardness may be determined by LLM based on user phrasing.
    """

    attribute: str
    value: str
    hardness: float = HARDNESS_DISCLOSED
    range: AttributeRange | None = None

    @property
    def is_hard(self) -> bool:
        return self.hardness >= HARDNESS_REQUIREMENT


@dataclass
class PreferenceStore:
    """Collection of Preferences plus session metadata — the agent's full memory.

    Used by the Ranker as the resource for ranking decisions.
    """

    profile_tags: list[str]
    category: str = ""
    initial_preference: str = ""
    preferences: list[Preference] = field(default_factory=list)
    asked_attributes: list[str] = field(default_factory=list)
    declined_attributes: set[str] = field(default_factory=set)
    seen_recommendations: set[str] = field(default_factory=set)
    broad_answers: int = 0
    broad_exhausted: bool = False

    def add_preference(self, attribute: str, value: str, hardness: float = HARDNESS_DISCLOSED) -> bool:
        """Add a preference if not a duplicate. Returns True if added."""
        cleaned = _clean_value(value)
        if not cleaned:
            return False
        norm = _normalized(cleaned)
        if not norm or any(_normalized(p.value) == norm for p in self.preferences):
            return False
        self.preferences.append(Preference(attribute=attribute, value=cleaned, hardness=hardness))
        return True

    def remove_preference_by_value(self, value: str) -> None:
        """Remove a preference whose normalized value matches."""
        norm = _normalized(value)
        self.preferences = [p for p in self.preferences if _normalized(p.value) != norm]

    @property
    def constraint_values(self) -> list[str]:
        """Raw value strings for all preferences (backward compat with Ranker)."""
        return [p.value for p in self.preferences]

    def hard_preferences(self) -> list[Preference]:
        """Preferences that are hard requirements."""
        return [p for p in self.preferences if p.is_hard]

    def soft_preferences(self) -> list[Preference]:
        """Preferences that are soft / nice-to-have."""
        return [p for p in self.preferences if not p.is_hard]

    def next_question(self, broad_question_limit: int = 2) -> tuple[str, str]:
        """Pick the next clarification question. Returns (message, ask_attribute)."""
        if not self.broad_exhausted and self.broad_answers < broad_question_limit:
            self.asked_attributes.append("other")
            if self.broad_answers == 0:
                return (
                    "What matters most to you\u2014such as material, color, fit, budget, or intended use?",
                    "other",
                )
            return ("Is there one more must-have detail I should prioritize?", "other")

        narrowable = self._range_narrowing_candidate()
        if narrowable is not None:
            label = narrowable.attribute.replace("_", " ")
            return (
                f"You mentioned {narrowable.value}. Could you be more specific about {label}?",
                narrowable.attribute,
            )

        for attr in QUESTION_ORDER:
            if attr not in self.asked_attributes and attr not in self.declined_attributes:
                self.asked_attributes.append(attr)
                label = attr.replace("_", " ")
                return (f"Do you have a preference for {label}?", attr)

        return ("Is there another requirement that would help narrow these down?", "other")

    def _range_narrowing_candidate(self) -> Preference | None:
        """Find the preference with the widest range that would benefit from narrowing.

        Returns None if many unasked attributes remain (new constraints are more
        productive early in the conversation) or if no range is wide enough.
        """
        BREADTH_THRESHOLD = 0.4
        unasked = sum(
            1 for attr in QUESTION_ORDER
            if attr not in self.asked_attributes and attr not in self.declined_attributes
        )
        if unasked >= 3:
            return None
        candidates = [
            p for p in self.preferences
            if p.range is not None and p.range.breadth() > BREADTH_THRESHOLD
        ]
        return max(candidates, key=lambda p: p.range.breadth()) if candidates else None
