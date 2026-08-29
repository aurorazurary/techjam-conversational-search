from __future__ import annotations

from starter.intents.base import Intent, CATEGORY_RE, classify_attribute


class BrowsingIntent(Intent):
    """Customer is exploring without strong constraints."""

    def __init__(self, message: str) -> None:
        super().__init__(scenario_signal="browsing", raw_text=message)
        cat_match = CATEGORY_RE.search(message)
        if cat_match:
            self.category_text = cat_match.group(1).strip()
        # Try to extract trailing constraint text (e.g. intent_override initial turn)
        parts = message.split(".", 1)
        if len(parts) > 1 and parts[1].strip():
            tail = parts[1].strip().rstrip(".")
            if tail and len(tail) > 3:
                self.constraints.append({
                    "attribute": classify_attribute(tail),
                    "value": tail,
                })
