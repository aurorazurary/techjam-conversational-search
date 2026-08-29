from __future__ import annotations

from starter.intents.base import Intent


class NoInfoIntent(Intent):
    """No actionable information in the message."""

    def __init__(self, message: str) -> None:
        super().__init__(scenario_signal="no_info", raw_text=message)
