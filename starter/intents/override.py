from __future__ import annotations

from starter.intents.base import Intent, OVERRIDE_RE, classify_attribute
from starter.Preference import HARDNESS_OVERRIDE


class OverrideIntent(Intent):
    """Customer changes their preference mid-conversation."""

    def __init__(self, message: str) -> None:
        super().__init__(
            scenario_signal="override",
            override_signal=True,
            raw_text=message,
        )
        match = OVERRIDE_RE.search(message)
        if match:
            value = match.group(1).strip().rstrip(".")
            self.constraints.append({
                "attribute": classify_attribute(value),
                "value": value,
                "hardness": HARDNESS_OVERRIDE,
            })
