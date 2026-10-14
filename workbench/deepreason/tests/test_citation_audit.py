import json
import tempfile
import unittest
from pathlib import Path

from reasoning_agent_template.citation_audit import audit_claim_citations
from reasoning_agent_template.evidence import EvidenceLedger
from reasoning_agent_template.models import KnowledgeChunk, stable_hash


FIXTURE = Path(__file__).parent / "fixtures" / "technical_comparison.json"


class CitationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.scenario = json.loads(FIXTURE.read_text(encoding="utf-8"))
        ledger = EvidenceLedger(Path(self.temporary.name) / "ledger.jsonl")
        self.items = {}
        self.chunks = []
        for doc in self.scenario["documents"]:
            item = ledger.record(
                source_type="file",
                uri=doc["uri"],
                locator="fixture",
                content=doc["text"],
                summary=doc["text"],
                confidence=1.0,
                used_for=["offline-citation-audit"],
            )
            self.items[doc["id"]] = item
            self.chunks.append(
                KnowledgeChunk(
                    source=doc["uri"], span="fixture", text=doc["text"],
                    content_hash=stable_hash(doc["text"]), score=1.0, evidence_id=item.id,
                )
            )
        self.by_id = {item.id: item for item in self.items.values()}
        self.qualified = set(self.by_id)

    def _audit(self, case, *, gate_status="allow", qualified=None):
        review = {
            "claims": [{
                "claim_id": case["id"],
                "statement": case["claim"],
                "evidence_id": self.items[case["source"]].id,
                "excerpt": case["excerpt"],
            }]
        }
        return audit_claim_citations(
            review,
            gate_status=gate_status,
            qualified_evidence_ids=self.qualified if qualified is None else qualified,
            evidence=self.by_id,
            chunks=self.chunks,
        )

    def test_fixture_separates_structural_checks_from_semantic_support(self):
        for case in self.scenario["cases"]:
            with self.subTest(case=case["id"]):
                result = self._audit(case)
                self.assertEqual(result.status, case["expected_structure"])
        self.assertEqual(
            self._audit(self.scenario["cases"][3]).status,
            "structurally_valid_semantics_unchecked",
        )

    def test_gate_and_qualification_cannot_be_overridden_by_review(self):
        valid = self.scenario["cases"][0]
        self.assertEqual(self._audit(valid, gate_status="deny").status, "blocked")
        unqualified = self._audit(valid, qualified=set())
        self.assertEqual(unqualified.reasons, ("claim_0:unqualified_evidence_id",))

    def test_missing_or_changed_source_fails_closed(self):
        valid = self.scenario["cases"][0]
        self.assertEqual(
            audit_claim_citations(
                {"claims": []}, gate_status="allow", qualified_evidence_ids=self.qualified,
                evidence=self.by_id, chunks=self.chunks,
            ).status,
            "blocked",
        )
        changed = list(self.chunks)
        source = changed[1]
        changed[1] = KnowledgeChunk(
            source=source.source, span=source.span, text=source.text + " altered",
            content_hash=source.content_hash, score=source.score, evidence_id=source.evidence_id,
        )
        review = {"claims": [{
            "claim_id": "changed", "statement": valid["claim"],
            "evidence_id": self.items["v22"].id, "excerpt": valid["excerpt"],
        }]}
        result = audit_claim_citations(
            review, gate_status="allow", qualified_evidence_ids=self.qualified,
            evidence=self.by_id, chunks=changed,
        )
        self.assertIn("claim_0:source_hash_or_excerpt_mismatch", result.reasons)


if __name__ == "__main__":
    unittest.main()
