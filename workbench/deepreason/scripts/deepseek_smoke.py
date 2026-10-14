from __future__ import annotations

from pathlib import Path

from reasoning_agent_template.config import load_agent_config
from reasoning_agent_template.llm import ChatMessage, DeepSeekChatClient


def main() -> None:
    config = load_agent_config(Path("agent.yaml"))
    client = DeepSeekChatClient.from_config(config, role="worker")
    result = client.chat(
        [
            ChatMessage(
                role="system",
                content=(
                    "You are testing a heavy-reasoning agent template. "
                    "Return exactly one line starting with TEMPLATE_OK: ."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "After the prefix, write one short Chinese sentence saying that evidence-first reasoning, "
                    "state gates, and memory proposals are suitable constraints for an agent template."
                ),
            ),
        ],
        temperature=0,
        max_tokens=256,
    )
    if "TEMPLATE_OK" not in result.content:
        raise SystemExit("DeepSeek smoke test failed: TEMPLATE_OK marker missing")
    print(f"MODEL={result.model}")
    print("ANSWER=" + result.content.replace("\n", " ").strip())


if __name__ == "__main__":
    main()
