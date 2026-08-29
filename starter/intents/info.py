from __future__ import annotations

from starter.intents.base import Intent, MATTERS_RE, classify_attribute


class InfoIntent(Intent):
    """Customer discloses constraints in response to a question."""

    def __init__(self, message: str) -> None:
        super().__init__(scenario_signal="info", raw_text=message)
        matters = MATTERS_RE.search(message)
        if matters:
            raw = matters.group(1).strip().rstrip(".")
            for part in raw.split(";"):
                value = part.strip()
                if value:
                    self.constraints.append({
                        "attribute": classify_attribute(value),
                        "value": value,
                    })
