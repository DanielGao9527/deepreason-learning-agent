from __future__ import annotations

import json
import os
import http.client
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from reasoning_agent_template.config import AgentConfig


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
LOCAL_SECRET_PATH = Path("configs") / "secrets.local.json"


class MissingApiKeyError(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    raw: dict[str, Any]


class DeepSeekChatClient:
    """Small OpenAI-compatible DeepSeek chat client using stdlib HTTP."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        timeout_seconds: int = 60,
    ):
        if not api_key:
            raise MissingApiKeyError("Set DEEPSEEK_API_KEY before calling DeepSeek.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "DeepSeekChatClient":
        return cls(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            timeout_seconds=int(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        )

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        *,
        api_key: str | None = None,
        role: str = "worker",
    ) -> "DeepSeekChatClient":
        model_config = config.models.get(role, {})
        secrets = _load_local_secrets(config.workspace_root)
        return cls(
            api_key=api_key
            if api_key is not None
            else str(secrets.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")),
            model=str(
                secrets.get("deepseek_model")
                or model_config.get("model")
                or os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
            ),
            base_url=str(secrets.get("deepseek_base_url") or os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL)),
            timeout_seconds=int(secrets.get("deepseek_timeout_seconds") or os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        )

    @classmethod
    def is_configured(cls, config: AgentConfig) -> bool:
        secrets = _load_local_secrets(config.workspace_root)
        return bool(secrets.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY"))

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": [message.to_dict() for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMRequestError(f"DeepSeek HTTP {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise LLMRequestError(f"DeepSeek request failed: {exc.reason}") from exc
        except (TimeoutError, http.client.HTTPException, OSError) as exc:
            raise LLMRequestError(f"DeepSeek transport failed: {type(exc).__name__}: {exc}") from exc

        data = json.loads(body)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRequestError(f"DeepSeek response missing assistant content: {data}") from exc
        return ChatResult(content=content, model=str(data.get("model", self.model)), raw=data)


def _load_local_secrets(workspace_root: Path) -> dict[str, Any]:
    path = Path(workspace_root) / LOCAL_SECRET_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MissingApiKeyError(f"Cannot read local DeepSeek secret file: {path}") from exc
    if not isinstance(data, dict):
        raise MissingApiKeyError(f"Local DeepSeek secret file must be a JSON object: {path}")
    return data
