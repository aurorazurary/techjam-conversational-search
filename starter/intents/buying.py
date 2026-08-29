from __future__ import annotations

from starter.intents.base import Intent, CATEGORY_RE, REQUIREMENT_RE, classify_attribute


class BuyingIntent(Intent):
    """Customer has a clear requirement from the start."""

    def __init__(self, message: str) -> None:
        super().__init__(scenario_signal="buying", raw_text=message)
        cat_match = CATEGORY_RE.search(message)
        if cat_match:
            self.category_text = cat_match.group(1).strip()
        req = REQUIREMENT_RE.search(message)
        if req:
            value = req.group(1).strip().rstrip(".")
            self.constraints.append({
                "attribute": classify_attribute(value),
                "value": value,
            })
