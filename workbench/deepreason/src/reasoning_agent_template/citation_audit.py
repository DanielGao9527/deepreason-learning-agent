"""Check the mechanical provenance of a proposed claim-to-evidence map.

This deliberately does not determine whether an excerpt semantically entails a
claim. A structurally valid result must still be judged for factual support.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from reasoning_agent_template.models import EvidenceItem, KnowledgeChunk, stable_hash


@dataclass(frozen=True)
class CitationAudit:
    status: str
    reasons: tuple[str, ...]
    checked_claims: int


def audit_claim_citations(
    review: Any,
    *,
    gate_status: str,
    qualified_evidence_ids: set[str],
    evidence: Mapping[str, EvidenceItem],
    chunks: Sequence[KnowledgeChunk],
) -> CitationAudit:
    """Reject unknown IDs, changed source text, and excerpts absent from the source."""
    if gate_status != "allow":
        return CitationAudit("blocked", (f"gate_{gate_status}",), 0)
    if not isinstance(review, dict) or not isinstance(review.get("claims"), list):
        return CitationAudit("blocked", ("invalid_review_schema",), 0)
    claims = review["claims"]
    if not claims:
        return CitationAudit("blocked", ("no_claims_submitted",), 0)

    by_id: dict[str, list[KnowledgeChunk]] = {}
    for chunk in chunks:
        by_id.setdefault(chunk.evidence_id, []).append(chunk)
    reasons: list[str] = []
    seen_claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            reasons.append(f"claim_{index}:invalid_schema")
            continue
        claim_id = claim.get("claim_id")
        statement = claim.get("statement")
        evidence_id = claim.get("evidence_id")
        excerpt = claim.get("excerpt")
        if not all(isinstance(value, str) and value.strip() for value in (claim_id, statement, evidence_id, excerpt)):
            reasons.append(f"claim_{index}:missing_field")
            continue
        if claim_id in seen_claim_ids:
            reasons.append(f"claim_{index}:duplicate_claim_id")
        seen_claim_ids.add(claim_id)
        if evidence_id not in qualified_evidence_ids:
            reasons.append(f"claim_{index}:unqualified_evidence_id")
            continue
        item = evidence.get(evidence_id)
        source_chunks = by_id.get(evidence_id, [])
        if item is None or not source_chunks:
            reasons.append(f"claim_{index}:source_missing")
            continue
        if not any(
            stable_hash(chunk.text) == item.content_hash == chunk.content_hash
            and excerpt in chunk.text
            for chunk in source_chunks
        ):
            reasons.append(f"claim_{index}:source_hash_or_excerpt_mismatch")
    return CitationAudit(
        status="blocked" if reasons else "structurally_valid_semantics_unchecked",
        reasons=tuple(reasons),
        checked_claims=len(claims),
    )
