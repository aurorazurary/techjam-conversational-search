from __future__ import annotations

from starter.intents.base import Intent


class BoundaryIntent(Intent):
    """Customer has no preference for a requested attribute."""

    def __init__(self, message: str, attribute: str) -> None:
        super().__init__(
            scenario_signal="boundary",
            no_preference_attr=attribute,
            raw_text=message,
        )
