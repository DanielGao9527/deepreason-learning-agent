from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from reasoning_agent_template.agents_spec import AgentsSpec, AgentsSpecStore
from reasoning_agent_template.models import GateDecision, stable_hash
from reasoning_agent_template.workflow_spec import WorkflowSpec, WorkflowSpecStore


ALLOWED_CODE_MODIFIER_PREFIXES = (
    "src/",
    "tests/",
    "configs/workflows/",
    "configs/agents/",
    ".opencode/agents/code-modifier.md",
)
DENIED_CODE_MODIFIER_PREFIXES = (
    "configs/secrets",
    "memory/",
    "evidence/",
    "logs/",
)


@dataclass(frozen=True)
class CodeModifierResult:
    status: str
    proposal_id: str
    draft_hash: str
    modified_files: list[str] = field(default_factory=list)
    test_command: str = ""
    gate_decision: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CodeModifierAdapter(Protocol):
    def apply_workflow_proposal(self, proposal: dict[str, Any], *, approved_by: str | None = None) -> CodeModifierResult:
        ...

    def apply_agents_proposal(self, proposal: dict[str, Any], *, approved_by: str | None = None) -> CodeModifierResult:
        ...


class LocalWorkflowSpecCodeModifier:
    """Apply approved workflow specs to allowed config files only.

    This adapter is intentionally narrow: it is the safe default for the debug
    console. More capable AI code editing can be plugged in through
    OpenCodeCodeModifier without changing API shape.
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root)

    def apply_workflow_proposal(self, proposal: dict[str, Any], *, approved_by: str | None = None) -> CodeModifierResult:
        proposal_id = str(proposal.get("proposal_id") or "")
        draft_hash = str(proposal.get("draft_hash") or "")
        target_path = str(proposal.get("target_path") or "")
        validation = proposal.get("validation") or {}
        modified_files = [str(item) for item in proposal.get("modified_files", [target_path]) if item]
        decision = self._gate(
            proposal_id=proposal_id,
            draft_hash=draft_hash,
            target_path=target_path,
            modified_files=modified_files,
            validation=validation,
            approved_by=approved_by,
        )
        if decision.status != "allow":
            return CodeModifierResult(
                status=decision.status,
                proposal_id=proposal_id,
                draft_hash=draft_hash,
                modified_files=modified_files,
                test_command=str(proposal.get("test_command") or ""),
                gate_decision=decision.to_dict(),
                message="code-modifier gate did not allow applying this proposal",
            )

        spec = WorkflowSpec.from_dict(dict(proposal.get("spec") or {}))
        target = (self.workspace_root / target_path).resolve()
        self._ensure_allowed_target(target, modified_files)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        proposal["status"] = "applied"
        proposal["approved_by"] = approved_by
        WorkflowSpecStore(self.workspace_root).save_proposal(proposal)
        return CodeModifierResult(
            status="applied",
            proposal_id=proposal_id,
            draft_hash=draft_hash,
            modified_files=modified_files,
            test_command=str(proposal.get("test_command") or ""),
            gate_decision=decision.to_dict(),
            message="workflow spec applied by local code-modifier adapter",
        )

    def apply_agents_proposal(self, proposal: dict[str, Any], *, approved_by: str | None = None) -> CodeModifierResult:
        proposal_id = str(proposal.get("proposal_id") or "")
        draft_hash = str(proposal.get("draft_hash") or "")
        target_path = str(proposal.get("target_path") or "")
        validation = proposal.get("validation") or {}
        modified_files = [str(item) for item in proposal.get("modified_files", [target_path]) if item]
        decision = self._gate(
            proposal_id=proposal_id,
            draft_hash=draft_hash,
            target_path=target_path,
            modified_files=modified_files,
            validation=validation,
            approved_by=approved_by,
        )
        if decision.status != "allow":
            return CodeModifierResult(
                status=decision.status,
                proposal_id=proposal_id,
                draft_hash=draft_hash,
                modified_files=modified_files,
                test_command=str(proposal.get("test_command") or ""),
                gate_decision=decision.to_dict(),
                message="code-modifier gate did not allow applying this agents proposal",
            )

        spec = AgentsSpec.from_dict(dict(proposal.get("spec") or {}))
        target = (self.workspace_root / target_path).resolve()
        self._ensure_allowed_target(target, modified_files)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        proposal["status"] = "applied"
        proposal["approved_by"] = approved_by
        AgentsSpecStore(self.workspace_root).save_proposal(proposal)
        return CodeModifierResult(
            status="applied",
            proposal_id=proposal_id,
            draft_hash=draft_hash,
            modified_files=modified_files,
            test_command=str(proposal.get("test_command") or ""),
            gate_decision=decision.to_dict(),
            message="agents spec applied by local code-modifier adapter",
        )

    def _gate(
        self,
        *,
        proposal_id: str,
        draft_hash: str,
        target_path: str,
        modified_files: list[str],
        validation: dict[str, Any],
        approved_by: str | None,
    ) -> GateDecision:
        reasons: list[str] = []
        if not approved_by:
            reasons.append("approval is required")
        if validation.get("errors"):
            reasons.append("workflow validation has errors")
        if validation.get("requires_code"):
            reasons.append("workflow requires new code handler; local adapter can only apply workflow spec")
        for path in [target_path, *modified_files]:
            normalized = _normalize_relative(path)
            if any(normalized.startswith(prefix) for prefix in DENIED_CODE_MODIFIER_PREFIXES):
                reasons.append(f"denied path: {path}")
            if not any(normalized.startswith(prefix) for prefix in ALLOWED_CODE_MODIFIER_PREFIXES):
                reasons.append(f"path is outside code-modifier allowlist: {path}")
        return GateDecision(
            gate_id=f"gate_{stable_hash('|'.join([proposal_id, draft_hash, *reasons]))[:12]}",
            risk_level="medium",
            status="allow" if not reasons else "interrupt",
            reasons=reasons,
            required_evidence=[],
            approved_by=approved_by if not reasons else None,
        )

    def _ensure_allowed_target(self, target: Path, modified_files: list[str]) -> None:
        try:
            target.relative_to(self.workspace_root.resolve())
        except ValueError as exc:
            raise PermissionError(f"target escapes workspace: {target}") from exc
        for path in modified_files:
            normalized = _normalize_relative(path)
            if not any(normalized.startswith(prefix) for prefix in ALLOWED_CODE_MODIFIER_PREFIXES):
                raise PermissionError(f"path is outside code-modifier allowlist: {path}")


class OpenCodeCodeModifier:
    """Optional adapter that delegates code edits to the project code-modifier agent."""

    def __init__(self, workspace_root: str | Path, *, command: str = "opencode"):
        self.workspace_root = Path(workspace_root)
        self.command = command

    def apply_workflow_proposal(self, proposal: dict[str, Any], *, approved_by: str | None = None) -> CodeModifierResult:
        proposal_id = str(proposal.get("proposal_id") or "")
        draft_hash = str(proposal.get("draft_hash") or "")
        if not approved_by:
            decision = GateDecision(
                gate_id=f"gate_{stable_hash(proposal_id + draft_hash + 'missing-approval')[:12]}",
                risk_level="medium",
                status="interrupt",
                reasons=["approval is required"],
                required_evidence=[],
            )
            return CodeModifierResult(
                status="interrupt",
                proposal_id=proposal_id,
                draft_hash=draft_hash,
                gate_decision=decision.to_dict(),
                message="approval is required before invoking OpenCode code-modifier",
            )
        prompt = (
            "Apply this approved workflow proposal. Only modify allowed code/config paths. "
            "Run the test command if feasible and report results.\n\n"
            + json.dumps(proposal, ensure_ascii=False, indent=2)
        )
        completed = subprocess.run(
            [self.command, "run", "--agent", "code-modifier", prompt],
            cwd=self.workspace_root,
            text=True,
            capture_output=True,
            timeout=240,
            check=False,
        )
        status = "applied" if completed.returncode == 0 else "failed"
        return CodeModifierResult(
            status=status,
            proposal_id=proposal_id,
            draft_hash=draft_hash,
            modified_files=[str(item) for item in proposal.get("modified_files", [])],
            test_command=str(proposal.get("test_command") or ""),
            message=f"opencode code-modifier exited with {completed.returncode}",
            output=(completed.stdout + completed.stderr)[-4000:],
        )

    def apply_agents_proposal(self, proposal: dict[str, Any], *, approved_by: str | None = None) -> CodeModifierResult:
        return self.apply_workflow_proposal(proposal, approved_by=approved_by)


def _normalize_relative(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")
