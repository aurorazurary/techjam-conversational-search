from __future__ import annotations

from starter.Intent import (
    Intent,
    classify_attribute,
    CATEGORY_RE,
    REQUIREMENT_RE,
    MATTERS_RE,
    OVERRIDE_RE,
    NO_PREF_RE,
    NO_ADDITIONAL_RE,
)


class IntentGenerator:
    """Generates Intent from user messages.

    Currently uses rule-based extraction.
    TODO: Subclass or replace with LLM-based generation.
    """

    def generate(self, message: str, turn: int) -> Intent:
        """Parse a user message into a structured Intent.

        This is the method to override with LLM-based intent detection.
        """
        return self._generate_rule_based(message, turn)

    def _generate_rule_based(self, message: str, turn: int) -> Intent:
        """Rule-based intent extraction from evaluator message patterns."""
        intent = Intent(raw_text=message)

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
                intent.scenario_signal = "browsing"
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

        # --- Fallback ---
        intent.scenario_signal = "no_info"
        return intent
