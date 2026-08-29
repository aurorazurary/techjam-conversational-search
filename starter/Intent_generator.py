from __future__ import annotations

from starter.intents import (
    Intent,
    BuyingIntent,
    BrowsingIntent,
    OverrideIntent,
    BoundaryIntent,
    InfoIntent,
    NoInfoIntent,
)
from starter.intents.base import NO_PREF_RE, NO_ADDITIONAL_RE, MATTERS_RE


class IntentGenerator:
    """Factory that routes a user message to the appropriate Intent subclass.

    TODO: Override generate() with LLM-based detection that returns the
    correct Intent subclass based on LLM output instead of keyword matching.
    """

    def generate(self, message: str, turn: int) -> Intent:
        """Detect intent type and return the corresponding subclass instance."""
        return self._generate_rule_based(message, turn)

    def _generate_rule_based(self, message: str, turn: int) -> Intent:
        # --- Override detection (any turn) ---
        if "actually, ignore" in message.lower():
            return OverrideIntent(message)

        # --- Boundary / no-preference ---
        no_pref = NO_PREF_RE.search(message)
        if no_pref:
            return BoundaryIntent(message, no_pref.group(1).lower())

        # --- No additional preference ---
        if NO_ADDITIONAL_RE.search(message):
            return NoInfoIntent(message)

        # --- Turn 1: buying vs browsing ---
        if turn == 1:
            if "key requirement is:" in message.lower():
                return BuyingIntent(message)
            return BrowsingIntent(message)

        # --- Turn > 1: constraint disclosure ---
        if MATTERS_RE.search(message):
            return InfoIntent(message)

        # --- Ask-me-about / fallback ---
        return NoInfoIntent(message)
