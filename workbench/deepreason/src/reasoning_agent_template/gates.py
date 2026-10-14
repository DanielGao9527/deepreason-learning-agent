from __future__ import annotations

from pathlib import Path

from reasoning_agent_template.models import EvidenceItem, GateDecision, stable_hash


class GatePolicy:
    """Evidence, approval, and workspace boundary checks for risky actions."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        min_evidence_by_risk: dict[str, int] | None = None,
        approval_required_actions: set[str] | list[str] | None = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.min_evidence_by_risk = {
            "none": 0,
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 2,
            **(min_evidence_by_risk or {}),
        }
        self.approval_required_actions = set(approval_required_actions or [])

    def evaluate(
        self,
        *,
        action: str,
        risk_level: str,
        evidence: list[EvidenceItem],
        target_path: Path | None = None,
        approved_by: str | None = None,
        state_snapshot_id: str | None = None,
    ) -> GateDecision:
        reasons: list[str] = []
        status = "allow"

        if target_path is not None and not self._inside_workspace(target_path):
            reasons.append(f"target path is outside workspace: {target_path}")
            status = "deny"

        required_count = self.min_evidence_by_risk.get(risk_level, 1)
        if len(evidence) < required_count:
            reasons.append(
                f"{risk_level} action requires at least {required_count} evidence item(s); got {len(evidence)}"
            )
            if status != "deny":
                status = "interrupt"

        if action in self.approval_required_actions and not approved_by:
            reasons.append(f"{action} requires human approval")
            if status != "deny":
                status = "interrupt"

        gate_id = f"gate_{stable_hash('|'.join([action, risk_level, status, *reasons]))[:12]}"
        return GateDecision(
            gate_id=gate_id,
            risk_level=risk_level,
            status=status,
            reasons=reasons,
            required_evidence=[item.id for item in evidence],
            approved_by=approved_by,
            state_snapshot_id=state_snapshot_id,
        )

    def _inside_workspace(self, target_path: Path) -> bool:
        target = Path(target_path)
        if not target.is_absolute():
            target = self.workspace_root / target
        try:
            target.resolve(strict=False).relative_to(self.workspace_root)
            return True
        except ValueError:
            return False
