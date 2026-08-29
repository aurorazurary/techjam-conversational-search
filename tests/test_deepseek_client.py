from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starter.deepseek_client import DeepSeekClient


class FakeHTTPResponse:
    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 4,
                    "prompt_cache_hit_tokens": 7,
                    "prompt_cache_miss_tokens": 4,
                },
            }
        ).encode()


class DeepSeekClientTest(unittest.TestCase):
    def test_json_request_and_usage_parsing(self) -> None:
        captured: dict = {}

        def fake_urlopen(request: object, timeout: float) -> FakeHTTPResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeHTTPResponse()

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "deepseek.jsonl"
            client = DeepSeekClient(
                "test-key", timeout_seconds=1.25, log_path=log_path
            )
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                response = client.complete_json(
                    "Return JSON.", {"message": "hello"}
                )
            log_text = log_path.read_text(encoding="utf-8")
            log_record = json.loads(log_text)

        request = captured["request"]
        body = json.loads(request.data.decode())
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(captured["timeout"], 1.25)
        self.assertEqual(response.payload, {"ok": True})
        self.assertEqual(response.prompt_tokens, 11)
        self.assertEqual(response.completion_tokens, 4)
        self.assertEqual(response.prompt_cache_hit_tokens, 7)
        self.assertEqual(response.prompt_cache_miss_tokens, 4)
        self.assertGreaterEqual(response.latency_seconds, 0.0)
        self.assertNotIn("test-key", log_text)
        self.assertEqual(log_record["request"]["user_payload"]["message"], "hello")
        self.assertEqual(log_record["response"]["payload"], {"ok": True})
        self.assertEqual(log_record["usage"]["total_tokens"], 15)


if __name__ == "__main__":
    unittest.main()
