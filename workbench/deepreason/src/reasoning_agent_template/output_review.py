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
    required_coverage: Sequence[str] = (),
    review_context_hash: str = "",
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
    coverage_errors = _coverage_errors(draft, review, required_coverage)
    if coverage_errors:
        return _withheld(gate_status, "answer_coverage_contract_failed", 0, coverage_errors)
    if review_context_hash and review.get("review_context_hash") != review_context_hash:
        return _withheld(gate_status, "review_context_mismatch", 0)
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


def _coverage_errors(draft: str, review: Mapping[str, Any], required: Sequence[str]) -> tuple[str, ...]:
    """Check completeness and exact draft provenance, not semantic adequacy."""
    if not required:
        return ()
    coverage = review.get("coverage")
    if not isinstance(coverage, list) or len(coverage) != len(required):
        return ("missing_or_extra_coverage",)
    expected = set(required)
    seen_ids: set[str] = set()
    seen_excerpts: set[str] = set()
    errors: list[str] = []
    for index, item in enumerate(coverage):
        if not isinstance(item, dict):
            errors.append(f"coverage_{index}:invalid_schema")
            continue
        point_id = item.get("point_id")
        excerpt = item.get("draft_excerpt")
        if not isinstance(point_id, str) or point_id not in expected or point_id in seen_ids:
            errors.append(f"coverage_{index}:unknown_or_duplicate_point")
            continue
        seen_ids.add(point_id)
        if item.get("status") != "covered":
            errors.append(f"coverage_{index}:not_covered")
        if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in draft:
            errors.append(f"coverage_{index}:excerpt_missing_from_draft")
        elif excerpt in seen_excerpts:
            errors.append(f"coverage_{index}:reused_excerpt")
        else:
            seen_excerpts.add(excerpt)
    if seen_ids != expected:
        errors.append("coverage_ids_incomplete")
    return tuple(errors)


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
