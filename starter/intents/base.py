from __future__ import annotations

import re
from dataclasses import dataclass, field

MATERIALS = ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")

CATEGORY_RE = re.compile(r"I'm looking for (.+?)(?:\.|,)", re.I)
REQUIREMENT_RE = re.compile(r"A key requirement is:\s*(.+?)\.?\s*$", re.I)
MATTERS_RE = re.compile(r"what matters is:\s*(.+?)\.?\s*$", re.I)
OVERRIDE_RE = re.compile(r"What I need is:\s*(.+?)\.?\s*$", re.I)
NO_PREF_RE = re.compile(r"I don't have a preference for (\w+)", re.I)
NO_ADDITIONAL_RE = re.compile(r"I don't have an additional preference for (\w+)", re.I)


def classify_attribute(value: str) -> str:
    """Classify a constraint string into an attribute type.

    Returns one of: budget, material, color, size, style, use_case, feature.

    TODO: Replace with LLM-based classification for better accuracy on
    ambiguous constraints. The LLM version should accept the same input/output
    contract: (value: str) -> str returning one of the attribute types above.
    """
    return _classify_attribute_rule_based(value)


def _classify_attribute_rule_based(value: str) -> str:
    """Rule-based fallback. Mirrors evaluator/local_evaluator.py:classify_constraint."""
    lowered = value.lower()
    if "budget" in lowered or re.search(r"(?:\$|<=|under)\s*\d", lowered):
        return "budget"
    if any(m in lowered for m in MATERIALS):
        return "material"
    if any(w in lowered for w in ("color", "black", "white", "blue", "red", "pink", "green",
                                   "brown", "gray", "grey", "purple", "yellow", "orange")):
        return "color"
    if any(w in lowered for w in ("size", "sizing", "width", "wide", "narrow")):
        return "size"
    if any(w in lowered for w in ("department", "style", "fit", "sleeve", "neck")):
        return "style"
    if any(w in lowered for w in ("hiking", "running", "gym", "winter", "outdoor", "work")):
        return "use_case"
    return "feature"


@dataclass
class Intent:
    """Base intent. Subclasses represent specific scenario types."""

    scenario_signal: str = "unknown"
    category_text: str = ""
    constraints: list[dict] = field(default_factory=list)
    override_signal: bool = False
    no_preference_attr: str | None = None
    replace_attribute: str | None = None
    shopping_mode: str = "unknown"
    confidence: float = 1.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_text: str = ""

    @classmethod
    def from_message(cls, message: str, turn: int) -> Intent:
        from starter.Intent_generator import IntentGenerator
        return IntentGenerator().generate(message, turn)
