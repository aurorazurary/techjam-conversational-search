from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class DeepSeekError(RuntimeError):
    """Raised when a DeepSeek request cannot produce a usable response."""


@dataclass(frozen=True)
class DeepSeekJSONResponse:
    payload: dict
    prompt_tokens: int
    completion_tokens: int
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    latency_seconds: float = 0.0


class DeepSeekClient:
    """Minimal standard-library client for DeepSeek JSON chat completions."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 4.0,
        log_path: str | Path | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DeepSeek API key must not be empty")
        self._api_key = api_key
        self.model = model.strip() or DEFAULT_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.log_path = Path(log_path) if log_path else None

    @classmethod
    def from_env(cls) -> DeepSeekClient | None:
        """Build a client from environment variables, or return None offline."""
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            timeout = float(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "4.0"))
        except ValueError:
            timeout = 4.0
        return cls(
            api_key,
            model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            timeout_seconds=timeout,
            log_path=os.environ.get("DEEPSEEK_LOG_PATH") or None,
        )

    def complete_json(self, system_prompt: str, user_payload: dict) -> DeepSeekJSONResponse:
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=True),
                },
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 500,
            "stream": False,
        }
        body = json.dumps(request_payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started_at = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise DeepSeekError("DeepSeek request failed") from error

        try:
            content = envelope["choices"][0]["message"]["content"]
            payload = json.loads(content)
            usage = envelope.get("usage") or {}
            prompt_tokens = max(0, int(usage.get("prompt_tokens", 0)))
            completion_tokens = max(0, int(usage.get("completion_tokens", 0)))
            prompt_cache_hit_tokens = max(
                0, int(usage.get("prompt_cache_hit_tokens", 0))
            )
            prompt_cache_miss_tokens = max(
                0, int(usage.get("prompt_cache_miss_tokens", 0))
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise DeepSeekError("DeepSeek returned an invalid JSON completion") from error
        if not isinstance(payload, dict):
            raise DeepSeekError("DeepSeek JSON completion must be an object")
        latency_seconds = time.perf_counter() - started_at
        result = DeepSeekJSONResponse(
            payload,
            prompt_tokens,
            completion_tokens,
            prompt_cache_hit_tokens,
            prompt_cache_miss_tokens,
            latency_seconds,
        )
        self._append_log(
            {
                "schema_version": 1,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
                "request": {
                    "system_prompt": system_prompt,
                    "user_payload": user_payload,
                    "settings": {
                        "response_format": request_payload["response_format"],
                        "thinking": request_payload["thinking"],
                        "temperature": request_payload["temperature"],
                        "max_tokens": request_payload["max_tokens"],
                    },
                },
                "response": {
                    "raw_content": content,
                    "payload": payload,
                },
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
                    "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
                },
                "latency_seconds": latency_seconds,
            }
        )
        return result

    def _append_log(self, record: dict) -> None:
        """Append one secret-free interaction record without affecting inference."""
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # Exporting diagnostics must never make the shopping agent fail.
            return
