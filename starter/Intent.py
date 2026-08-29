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

    Mirrors evaluator/local_evaluator.py:classify_constraint exactly.
    """
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
    """Structured representation of a single user message."""

    scenario_signal: str = "unknown"
    category_text: str = ""
    constraints: list[dict] = field(default_factory=list)
    override_signal: bool = False
    no_preference_attr: str | None = None
    raw_text: str = ""

    @classmethod
    def from_message(cls, message: str, turn: int) -> Intent:
        intent = cls(raw_text=message)

        # --- Override detection (any turn) ---
        if "Actually, ignore" in message or "actually, ignore" in message:
            intent.override_signal = True
            intent.scenario_signal = "override"
            match = OVERRIDE_RE.search(message)
            if match:
                value = match.group(1).strip().rstrip(".")
                intent.constraints.append({
                    "attribute": classify_attribute(value),
                    "value": value,
                })
            return intent

        # --- Boundary / no-preference detection ---
        no_pref = NO_PREF_RE.search(message)
        if no_pref:
            intent.no_preference_attr = no_pref.group(1).lower()
            intent.scenario_signal = "boundary"
            return intent

        # --- No additional preference ---
        no_add = NO_ADDITIONAL_RE.search(message)
        if no_add:
            intent.scenario_signal = "no_info"
            return intent

        # --- Turn 1: scenario + category ---
        if turn == 1:
            cat_match = CATEGORY_RE.search(message)
            if cat_match:
                intent.category_text = cat_match.group(1).strip()

            if "A key requirement is:" in message or "key requirement is:" in message:
                intent.scenario_signal = "buying"
                req = REQUIREMENT_RE.search(message)
                if req:
                    value = req.group(1).strip().rstrip(".")
                    intent.constraints.append({
                        "attribute": classify_attribute(value),
                        "value": value,
                    })
            elif "still exploring" in message.lower():
                intent.scenario_signal = "browsing"
            else:
                # Could be intent_override initial (has soft preference text)
                # or unrecognised — extract any trailing constraint-like text
                intent.scenario_signal = "browsing"
                # Try to extract constraint from patterns like "I'm looking for X. <constraint>"
                parts = message.split(".", 1)
                if len(parts) > 1 and parts[1].strip():
                    tail = parts[1].strip().rstrip(".")
                    if tail and len(tail) > 3:
                        intent.constraints.append({
                            "attribute": classify_attribute(tail),
                            "value": tail,
                        })
            return intent

        # --- Turn > 1: constraint disclosure ---
        matters = MATTERS_RE.search(message)
        if matters:
            intent.scenario_signal = "info"
            raw = matters.group(1).strip().rstrip(".")
            for part in raw.split(";"):
                value = part.strip()
                if value:
                    intent.constraints.append({
                        "attribute": classify_attribute(value),
                        "value": value,
                    })
            return intent

        # --- Ask-me-about-one-attribute signal ---
        if "ask me about one specific attribute" in message.lower():
            intent.scenario_signal = "no_info"
            return intent

        # --- Fallback: try to extract any useful text ---
        intent.scenario_signal = "no_info"
        return intent
