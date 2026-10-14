from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from reasoning_agent_template.config import AgentConfig


class ConfigAssistant:
    """Deterministic helper used by the template's configurator agent."""

    def __init__(self, schema: dict[str, Any]):
        self.schema = schema

    @classmethod
    def from_schema(cls, path: Path) -> "ConfigAssistant":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def create_project_config(
        self,
        *,
        name: str,
        purpose: str,
        audience: str,
        knowledge_dir: str,
    ) -> dict[str, Any]:
        config = deepcopy(AgentConfig.default(workspace_root=Path(".")).__dict__)
        config.pop("workspace_root", None)
        config["identity"]["name"] = name
        config["identity"]["purpose"] = purpose
        config["identity"]["audience"] = audience
        config["knowledge"]["directory"] = knowledge_dir
        return config

    def recommend_skills(self, needs: list[str]) -> list[str]:
        text = " ".join(needs).lower()
        rules = {
            "project-intake": ["goal", "scope", "project"],
            "evidence-first": ["evidence", "cite", "citation", "source"],
            "state-gates": ["gate", "approval", "permission", "risk"],
            "knowledge-rag": ["knowledge", "rag", "document", "retrieval"],
            "memory-consolidation": ["memory", "long-term", "short-term", "consolidation"],
            "minimal-change": ["minimal", "diff", "small", "modify"],
            "self-evolution": ["evolution", "self", "improve", "feedback"],
            "configurator": ["config", "configure", "agent.yaml"],
            "testing-verification": ["test", "verify", "regression", "acceptance"],
        }
        recommended = [skill for skill, terms in rules.items() if any(term in text for term in terms)]
        return recommended or ["project-intake", "evidence-first", "state-gates"]

    def generate_acceptance_tests(self, config: dict[str, Any]) -> list[str]:
        name = config["identity"]["name"]
        return [
            f"{name} answers a knowledge question with at least one evidence id in the final response.",
            f"{name} interrupts write_file or write_memory actions when evidence or approval is missing.",
            f"{name} keeps long-term memory writes partitioned and records memory evidence ids.",
            f"{name} generates self-evolution proposals under evolution/proposals without directly editing skills.",
        ]

    def write_yaml(self, config: dict[str, Any], target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump_yaml(config), encoding="utf-8")


def _dump_yaml(value: Any, indent: int = 0) -> str:
    spaces = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{spaces}{key}:")
                lines.append(_dump_yaml(item, indent + 2).rstrip())
            else:
                lines.append(f"{spaces}{key}: {_format_scalar(item)}")
        return "\n".join(lines) + "\n"
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{spaces}-")
                lines.append(_dump_yaml(item, indent + 2).rstrip())
            else:
                lines.append(f"{spaces}- {_format_scalar(item)}")
        return "\n".join(lines) + "\n"
    return f"{spaces}{_format_scalar(value)}\n"


def _format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if any(char in text for char in [":", "#", "{", "}", "[", "]"]) or not text:
        return json.dumps(text, ensure_ascii=False)
    return text
