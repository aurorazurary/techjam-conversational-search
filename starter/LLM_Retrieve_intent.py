from __future__ import annotations

from starter.Intent import Intent


def LLM_retrieve_intent(message: str, turn: int) -> tuple[Intent, dict]:
    """Extract intent using LLM with rule-based fallback.

    Returns (Intent, usage_dict).
    Currently delegates entirely to rule-based extraction.
    LLM integration can be added here later (Phase 3).
    """
    intent = Intent.from_message(message, turn)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    return intent, usage
