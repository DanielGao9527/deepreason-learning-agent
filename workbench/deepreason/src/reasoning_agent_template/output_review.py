"""Bounded decision for one model review of a strict-evidence answer draft."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from reasoning_agent_template.citation_audit import audit_claim_citations
from reasoning_agent_template.models import EvidenceItem, KnowledgeChunk
from reasoning_agent_template.release_policy import ReleaseDecision


WITHHELD_ANSWER = "本轮答案未通过证据与结论审查，暂不提供确定结论；请核对资料或缩小问题范围。"


@dataclass(frozen=True)
class OutputReviewOutcome:
    release: ReleaseDecision
    review_status: str
    checked_claims: int
    reasons: tuple[str, ...]


def decide_reviewed_release(
    draft: str,
    review: Any,
    *,
    gate_status: str,
    qualified_evidence_ids: set[str],
    evidence: Mapping[str, EvidenceItem],
    chunks: Sequence[KnowledgeChunk],
) -> OutputReviewOutcome:
    """A model's support label only releases a draft after structural checks.

    Model judgment is fallible; this does not establish semantic truth. Any
    invalid, uncertain, or issue result withholds the draft without revision.
    """
    if gate_status != "allow":
        return _withheld(gate_status, "gate_not_allowed", 0)
    if not isinstance(review, dict):
        return _withheld(gate_status, "invalid_review_schema", 0)
    status = review.get("review_status")
    if status != "supported":
        if status == "issue" and isinstance(review.get("findings"), list) and review["findings"]:
            return _withheld(gate_status, "model_found_issue", 0)
        if status == "uncertain":
            return _withheld(gate_status, "model_uncertain", 0)
        return _withheld(gate_status, "invalid_review_status", 0)
    if review.get("coverage_complete") is not True or review.get("findings") != []:
        return _withheld(gate_status, "coverage_or_findings_invalid", 0)
    audit = audit_claim_citations(
        review,
        gate_status=gate_status,
        qualified_evidence_ids=qualified_evidence_ids,
        evidence=evidence,
        chunks=chunks,
    )
    if audit.status != "structurally_valid_semantics_unchecked":
        return _withheld(gate_status, "citation_audit_failed", audit.checked_claims, audit.reasons)
    return OutputReviewOutcome(
        release=ReleaseDecision(
            answer=draft,
            status="released_model_reviewed",
            gate_status=gate_status,
            reason="model_reported_support; citations_structurally_valid; semantics_not_proven",
            draft_withheld=False,
        ),
        review_status="supported",
        checked_claims=audit.checked_claims,
        reasons=(),
    )


def _withheld(
    gate_status: str, reason: str, checked_claims: int, details: tuple[str, ...] = ()
) -> OutputReviewOutcome:
    return OutputReviewOutcome(
        release=ReleaseDecision(
            answer=WITHHELD_ANSWER,
            status="withheld",
            gate_status=gate_status,
            reason=reason,
            draft_withheld=True,
        ),
        review_status="not_supported",
        checked_claims=checked_claims,
        reasons=(reason, *details),
    )
