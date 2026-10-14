from __future__ import annotations

import json
from pathlib import Path

from reasoning_agent_template.models import EvidenceItem, EvolutionProposal, stable_hash, utc_now


class SelfEvolutionEngine:
    """Create reviewed evolution proposals without mutating skills directly."""

    def __init__(self, *, proposals_dir: Path, skills_dir: Path):
        self.proposals_dir = Path(proposals_dir)
        self.skills_dir = Path(skills_dir)

    def propose_skill_update(
        self,
        *,
        skill_name: str,
        rationale: str,
        evidence: list[EvidenceItem],
        suggested_change: str,
    ) -> EvolutionProposal:
        if not evidence:
            raise ValueError("self-evolution proposals require evidence")
        skill_path = self.skills_dir / skill_name / "SKILL.md"
        proposal_id = f"evo_{stable_hash(skill_name + rationale + suggested_change)[:12]}"
        target = f"skills/{skill_name}/SKILL.md"
        payload = {
            "proposal_id": proposal_id,
            "status": "proposed",
            "target": target,
            "created_at": utc_now(),
            "rationale": rationale,
            "suggested_change": suggested_change,
            "evidence_ids": [item.id for item in evidence],
            "requires_human_approval": True,
            "direct_mutation_performed": False,
            "target_exists": skill_path.exists(),
        }
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        path = self.proposals_dir / f"{proposal_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return EvolutionProposal(
            proposal_id=proposal_id,
            target=target,
            path=path,
            status="proposed",
            evidence_ids=[item.id for item in evidence],
        )
