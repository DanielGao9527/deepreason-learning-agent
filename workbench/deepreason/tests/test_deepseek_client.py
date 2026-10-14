import json
import os
import tempfile
import unittest
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from unittest.mock import patch

from reasoning_agent_template.config import AgentConfig
from reasoning_agent_template.llm import ChatMessage, DeepSeekChatClient, LLMRequestError, MissingApiKeyError


class _FakeResponse:
    def __init__(self, body: dict, status: int = 200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self):
        return json.dumps(self.body).encode("utf-8")


class DeepSeekClientTests(unittest.TestCase):
    def test_uses_openai_compatible_payload_and_parses_content(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse(
                {
                    "id": "chatcmpl-test",
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {"message": {"role": "assistant", "content": "pong"}}
                    ],
                }
            )

        client = DeepSeekChatClient(api_key="secret-test-key", model="deepseek-v4-flash")
        with patch("reasoning_agent_template.llm.request.urlopen", fake_urlopen):
            result = client.chat([ChatMessage(role="user", content="ping")], temperature=0)

        self.assertEqual(result.content, "pong")
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["payload"]["model"], "deepseek-v4-flash")
        self.assertEqual(captured["payload"]["messages"], [{"role": "user", "content": "ping"}])
        self.assertEqual(captured["payload"]["temperature"], 0)
        self.assertIn("Bearer secret-test-key", captured["headers"]["Authorization"])

    def test_network_read_failures_are_wrapped_as_llm_request_errors(self):
        failures = [
            TimeoutError("The read operation timed out"),
            IncompleteRead(b""),
            RemoteDisconnected("Remote end closed connection without response"),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                client = DeepSeekChatClient(api_key="secret-test-key", model="deepseek-v4-flash")

                def fake_urlopen(request, timeout):
                    raise failure

                with patch("reasoning_agent_template.llm.request.urlopen", fake_urlopen):
                    with self.assertRaises(LLMRequestError):
                        client.chat([ChatMessage(role="user", content="ping")], temperature=0)

    def test_missing_api_key_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingApiKeyError):
                DeepSeekChatClient.from_env()

    def test_can_be_created_from_agent_config(self):
        config = AgentConfig.default(workspace_root=Path("."))
        config.models["worker"] = {"provider": "deepseek", "model": "deepseek-v4-flash"}

        client = DeepSeekChatClient.from_config(config, api_key="secret-test-key", role="worker")

        self.assertEqual(client.model, "deepseek-v4-flash")

    def test_can_read_api_key_from_local_agent_secret_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets_dir = root / "configs"
            secrets_dir.mkdir()
            (secrets_dir / "secrets.local.json").write_text(
                json.dumps({"deepseek_api_key": "local-secret-key", "deepseek_model": "deepseek-v4-flash"}),
                encoding="utf-8",
            )
            config = AgentConfig.default(workspace_root=root)

            with patch.dict(os.environ, {}, clear=True):
                client = DeepSeekChatClient.from_config(config, role="worker")

        self.assertEqual(client.api_key, "local-secret-key")
        self.assertEqual(client.model, "deepseek-v4-flash")

    def test_local_secret_file_makes_configured_check_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir()
            (root / "configs" / "secrets.local.json").write_text(
                json.dumps({"deepseek_api_key": "local-secret-key"}),
                encoding="utf-8",
            )
            config = AgentConfig.default(workspace_root=root)

            with patch.dict(os.environ, {}, clear=True):
                configured = DeepSeekChatClient.is_configured(config)

        self.assertTrue(configured)

    def test_local_secret_file_allows_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir()
            (root / "configs" / "secrets.local.json").write_text(
                '\ufeff{"deepseek_api_key": "local-secret-key"}',
                encoding="utf-8",
            )
            config = AgentConfig.default(workspace_root=root)

            with patch.dict(os.environ, {}, clear=True):
                configured = DeepSeekChatClient.is_configured(config)

        self.assertTrue(configured)

    def test_smoke_script_exists_for_real_io(self):
        self.assertTrue((Path("scripts") / "deepseek_smoke.py").exists())


if __name__ == "__main__":
    unittest.main()
