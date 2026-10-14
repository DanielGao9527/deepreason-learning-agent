from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from reasoning_agent_template.models import GateDecision, stable_hash, utc_now


AGENTS_SPEC_VERSION = "1.0"
DEFAULT_AGENTS_SPEC_PATH = Path("configs/agents/default.agents.json")
DEFAULT_AGENTS_DRAFT_PATH = Path("configs/agents/default.agents.draft.json")
AGENTS_PROPOSAL_DIR = Path("configs/agents/proposals")


@dataclass(frozen=True)
class AgentRoleSpec:
    id: str
    label: str
    description: str
    responsibilities: list[str] = field(default_factory=list)
    model_role: str = "worker"
    tools: list[str] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    memory_access: list[str] = field(default_factory=list)
    workflow_nodes: list[str] = field(default_factory=list)
    handoff_contract: dict[str, Any] = field(default_factory=dict)
    ui: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentRoleSpec":
        agent_id = str(data.get("id") or data.get("name") or "").strip()
        return cls(
            id=agent_id,
            label=str(data.get("label") or agent_id),
            description=str(data.get("description") or ""),
            responsibilities=[str(item) for item in data.get("responsibilities", [])],
            model_role=str(data.get("model_role") or "worker"),
            tools=[str(item) for item in data.get("tools", [])],
            permissions=dict(data.get("permissions") or {}),
            memory_access=[str(item) for item in data.get("memory_access", [])],
            workflow_nodes=[str(item) for item in data.get("workflow_nodes", [])],
            handoff_contract=dict(data.get("handoff_contract") or {}),
            ui=dict(data.get("ui") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentsSpec:
    version: str
    name: str
    revision: str
    agents: list[AgentRoleSpec]
    protected_agents: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentsSpec":
        agents = [AgentRoleSpec.from_dict(item) for item in data.get("agents", [])]
        return cls(
            version=str(data.get("version") or AGENTS_SPEC_VERSION),
            name=str(data.get("name") or "default-agents"),
            revision=str(data.get("revision") or "dev"),
            agents=agents,
            protected_agents=[str(item) for item in data.get("protected_agents", [])],
        )

    @classmethod
    def default(cls) -> "AgentsSpec":
        return cls.from_dict(DEFAULT_AGENTS_SPEC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "revision": self.revision,
            "protected_agents": list(self.protected_agents),
            "agents": [agent.to_dict() for agent in self.agents],
        }

    def agent_map(self) -> dict[str, AgentRoleSpec]:
        return {agent.id: agent for agent in self.agents}

    def validate(self, *, base: "AgentsSpec | None" = None, workflow_agent_ids: set[str] | None = None) -> AgentValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if self.version != AGENTS_SPEC_VERSION:
            errors.append(f"unsupported agents spec version: {self.version}")
        if not self.agents:
            errors.append("agents spec must contain at least one agent")
        duplicate_agents = _duplicates(agent.id for agent in self.agents)
        errors.extend(f"duplicate agent id: {agent_id}" for agent_id in duplicate_agents)
        ids = {agent.id for agent in self.agents}
        for agent in self.agents:
            if not _VALID_ID.match(agent.id):
                errors.append(f"invalid agent id: {agent.id}")
            if not agent.description.strip():
                warnings.append(f"agent {agent.id} has no description")
        for protected in self.protected_agents:
            if protected not in ids:
                errors.append(f"protected agent is missing from agents: {protected}")
        if "coordinator" not in ids:
            warnings.append("coordinator agent is recommended")
        if "configurator" not in ids:
            warnings.append("configurator agent is recommended for guided setup")
        for workflow_agent in sorted(workflow_agent_ids or set()):
            if workflow_agent not in ids:
                warnings.append(f"workflow references agent not defined in agents spec: {workflow_agent}")
        if base is not None:
            missing_protected = [agent_id for agent_id in base.protected_agents if agent_id not in ids]
            errors.extend(f"protected agent cannot be deleted: {agent_id}" for agent_id in missing_protected)
        return AgentValidation(ok=not errors, errors=errors, warnings=warnings)


class AgentsSpecStore:
    def __init__(self, workspace_root: str | Path, config: dict[str, Any] | None = None):
        self.workspace_root = Path(workspace_root)
        self.config = dict(config or {})
        self.spec_path = _resolve_workspace_path(
            self.workspace_root,
            self.config.get("agents_spec") or DEFAULT_AGENTS_SPEC_PATH,
        )
        self.draft_path = _resolve_workspace_path(
            self.workspace_root,
            self.config.get("agents_draft") or DEFAULT_AGENTS_DRAFT_PATH,
        )
        self.proposal_dir = _resolve_workspace_path(
            self.workspace_root,
            self.config.get("agents_proposal_dir") or AGENTS_PROPOSAL_DIR,
        )

    def load(self) -> AgentsSpec:
        if self.spec_path.exists():
            return _read_spec(self.spec_path)
        return AgentsSpec.default()

    def load_draft(self) -> AgentsSpec | None:
        if not self.draft_path.exists():
            return None
        return _read_spec(self.draft_path)

    def save_draft(self, spec: AgentsSpec, *, workflow_agent_ids: set[str] | None = None) -> dict[str, Any]:
        self.draft_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(self.draft_path, spec.to_dict())
        validation = spec.validate(base=self.load(), workflow_agent_ids=workflow_agent_ids)
        return {"path": str(self.draft_path), "spec": spec.to_dict(), "validation": validation.to_dict()}

    def create_proposal(self, spec: AgentsSpec | None = None, *, workflow_agent_ids: set[str] | None = None) -> dict[str, Any]:
        base = self.load()
        candidate = spec or self.load_draft()
        if candidate is None:
            raise ValueError("agents draft is required before creating a proposal")
        validation = candidate.validate(base=base, workflow_agent_ids=workflow_agent_ids)
        draft_hash = stable_hash(_canonical_json(candidate.to_dict()))
        proposal_id = f"agp_{draft_hash[:12]}"
        target_relative = self.spec_path.relative_to(self.workspace_root).as_posix()
        proposal = {
            "proposal_id": proposal_id,
            "kind": "agents",
            "created_at": utc_now(),
            "status": "pending_approval",
            "draft_hash": draft_hash,
            "target_path": target_relative,
            "modified_files": [target_relative],
            "test_command": "python -m unittest discover -s tests -v",
            "validation": validation.to_dict(),
            "diff_preview": agents_diff(base, candidate),
            "spec": candidate.to_dict(),
            "gate_decision": GateDecision(
                gate_id=f"gate_{draft_hash[:12]}",
                risk_level="low",
                status="interrupt",
                reasons=["agents spec changes require explicit approval before code-modifier apply"],
                required_evidence=[],
            ).to_dict(),
        }
        self.proposal_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self.proposal_dir / f"{proposal_id}.json", proposal)
        return proposal

    def load_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal_path = self._proposal_path(proposal_id)
        if not proposal_path.exists():
            raise FileNotFoundError(f"agents proposal not found: {proposal_id}")
        return json.loads(proposal_path.read_text(encoding="utf-8"))

    def save_proposal(self, proposal: dict[str, Any]) -> None:
        proposal_id = str(proposal.get("proposal_id") or "")
        if not proposal_id:
            raise ValueError("proposal_id is required")
        self.proposal_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self._proposal_path(proposal_id), proposal)

    def _proposal_path(self, proposal_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", proposal_id)
        return self.proposal_dir / f"{safe_id}.json"


def load_agents_spec(workspace_root: str | Path, runtime_config: dict[str, Any] | None = None) -> AgentsSpec:
    return AgentsSpecStore(workspace_root, runtime_config).load()


def agents_diff(before: AgentsSpec, after: AgentsSpec) -> str:
    before_lines = _canonical_json(before.to_dict()).splitlines(keepends=True)
    after_lines = _canonical_json(after.to_dict()).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="current.agents.json",
            tofile="draft.agents.json",
        )
    )


def _read_spec(path: Path) -> AgentsSpec:
    return AgentsSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(_canonical_json(data) + "\n", encoding="utf-8")


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _resolve_workspace_path(workspace_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else workspace_root / path


def _duplicates(values: Any) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        text = str(value)
        if text in seen and text not in duplicates:
            duplicates.append(text)
        seen.add(text)
    return duplicates


_VALID_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_:-]*$")


DEFAULT_AGENTS_SPEC: dict[str, Any] = {
    "version": AGENTS_SPEC_VERSION,
    "name": "default-heavy-reasoning-agents",
    "revision": "baseline",
    "protected_agents": [
        "coordinator",
        "planner",
        "retriever",
        "reasoner",
        "critic",
        "memory",
        "reviewer",
        "configurator",
        "code_modifier",
    ],
    "agents": [
        {
            "id": "coordinator",
            "label": "协调器",
            "description": "负责运行调度、任务路由和状态机推进。",
            "responsibilities": ["判断任务难度和风险", "选择工作流", "组织 Agent 交付"],
            "model_role": "planner",
            "tools": ["workflow_status"],
            "memory_access": ["short_term:read", "long_term:read"],
            "workflow_nodes": ["intake", "act_or_answer", "respond"],
        },
        {
            "id": "planner",
            "label": "规划器",
            "description": "生成边界清晰、可审计的推理计划。",
            "responsibilities": ["拆解任务", "定义证据需求", "规划节点交付"],
            "model_role": "planner",
            "workflow_nodes": ["plan"],
        },
        {
            "id": "retriever",
            "label": "检索器",
            "description": "检索本地知识库、论文、外部来源和用户经验证据。",
            "responsibilities": ["RAG 检索", "外部证据检索", "证据归一化"],
            "model_role": "worker",
            "tools": ["retrieve_knowledge", "external_search"],
            "workflow_nodes": ["retrieve"],
        },
        {
            "id": "reasoner",
            "label": "推理器",
            "description": "基于检索证据、记忆和计划生成答案草案。",
            "responsibilities": ["综合证据", "生成草案", "标注不确定性"],
            "model_role": "worker",
            "workflow_nodes": ["reason"],
        },
        {
            "id": "critic",
            "label": "审查器",
            "description": "审计证据绑定、门禁结果和输出一致性。",
            "responsibilities": ["证据审计", "门禁审查", "验证输出"],
            "model_role": "critic",
            "workflow_nodes": ["evidence_audit", "gate", "verify"],
        },
        {
            "id": "memory",
            "label": "记忆管理",
            "description": "提出长期记忆沉淀候选，不直接写入保护资产。",
            "responsibilities": ["短期上下文整理", "长期记忆候选", "沉淀提案"],
            "model_role": "worker",
            "memory_access": ["short_term:read", "long_term:proposal"],
            "workflow_nodes": ["consolidate"],
        },
        {
            "id": "evolver",
            "label": "演进提案",
            "description": "根据失败案例、用户反馈和测试结果生成自进化提案。",
            "responsibilities": ["分析失败案例", "生成演进提案", "等待人工批准"],
            "model_role": "grader",
            "tools": ["proposal_writer"],
        },
        {
            "id": "reviewer",
            "label": "路由复核",
            "description": "审查 Coordinator 的难度、风险、证据需求和工作流选择，并可升级过松判断。",
            "responsibilities": ["复核路由", "升级证据需求", "记录审查理由"],
            "model_role": "critic",
        },
        {
            "id": "configurator",
            "label": "配置助手",
            "description": "通过问答帮助用户生成 Agent、Workflow、技能和验收测试草稿。",
            "responsibilities": ["理解用户目标", "生成多 Agent 草稿", "推荐工作流节点", "生成验收测试"],
            "model_role": "planner",
            "tools": ["agents_draft", "workflow_draft", "config_schema"],
            "permissions": {"direct_apply": False},
        },
        {
            "id": "code_modifier",
            "label": "代码修改器",
            "description": "只负责应用已批准的代码或配置修改，不参与普通对话、检索、记忆或推理。",
            "responsibilities": ["应用已批准提案", "限制修改路径", "运行验证命令"],
            "model_role": "worker",
            "tools": ["opencode:code-modifier"],
            "permissions": {"direct_apply": False, "allowed_paths": ["src/", "tests/", "configs/"]},
        },
    ],
}
