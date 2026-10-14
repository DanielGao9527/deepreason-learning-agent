import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reasoning_agent_template.config import AgentConfig
from reasoning_agent_template.llm import ChatResult, LLMRequestError
from reasoning_agent_template.models import KnowledgeChunk, stable_hash
from reasoning_agent_template.multiagent import MultiAgentOrchestrator
from reasoning_agent_template.sessions import SessionStore


FIXTURE = Path(__file__).parent / "fixtures" / "technical_comparison.json"


class OutputReviewClient:
    model = "offline-script"

    def __init__(self, mode, draft):
        self.mode = mode
        self.draft = draft
        self.evidence_id = None
        self.excerpt = None
        self.calls = []

    def chat(self, messages, *, temperature, max_tokens):
        prompt = "\n".join(item.content for item in messages)
        if "ROUTING_DECISION_JSON" in prompt:
            role = "coordinator"
            content = json.dumps({
                "source": "scripted", "difficulty": "hard", "workflow": "evidence_strict",
                "evidence_mode": "required", "evidence_strictness": "strict", "risk_level": "high",
                "category": "academic", "sources": ["papers"], "confidence": 0.8,
            })
        elif "REVIEW_DECISION_JSON" in prompt:
            role = "route_reviewer"
            content = json.dumps({"review_status": "approve", "findings": []})
        elif "OUTPUT_REVIEW_JSON" in prompt:
            role = "output_reviewer"
            if self.mode == "timeout":
                self.calls.append(role)
                raise LLMRequestError("offline simulated timeout")
            if self.mode == "invalid_json":
                content = "NOT_JSON"
            elif self.mode == "issue":
                content = json.dumps({
                    "review_status": "issue", "findings": ["claim conflicts with source"],
                    "coverage_complete": False, "claims": [],
                })
            else:
                content = json.dumps({
                    "review_status": "supported", "coverage_complete": True, "findings": [],
                    "claims": [{
                        "claim_id": "c1", "statement": self.draft,
                        "evidence_id": "ev_forged" if self.mode == "forged_id" else self.evidence_id,
                        "excerpt": self.excerpt,
                    }],
                })
        else:
            role = "worker"
            content = self.draft
        self.calls.append(role)
        return ChatResult(content=content, model=self.model, raw={"scripted": True})


class OutputReviewIntegrationTests(unittest.TestCase):
    def _run(self, mode, draft):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "knowledge").mkdir()
            config = AgentConfig.default(workspace_root=root)
            config.knowledge["directory"] = str(root / "knowledge")
            config.runtime["output_review_enabled"] = True
            client = OutputReviewClient(mode, draft)
            sessions = SessionStore(root / "sessions")
            orchestrator = MultiAgentOrchestrator(
                config=config, workspace_root=root, llm_client_factory=lambda _config: client,
                session_store=sessions,
            )
            documents = json.loads(FIXTURE.read_text(encoding="utf-8"))["documents"]

            def retrieve(searcher, query, *, top_k, sources):
                results = []
                for doc in documents:
                    item = searcher.ledger.record(
                        source_type="paper", uri=doc["uri"], locator="fixture", content=doc["text"],
                        summary=doc["text"], confidence=0.9, used_for=["offline-output-review"],
                    )
                    if doc["id"] == "v22":
                        client.evidence_id = item.id
                        client.excerpt = "The option must be enabled and a request ID supplied."
                    results.append(KnowledgeChunk(
                        source=doc["uri"], span="fixture", text=doc["text"],
                        content_hash=stable_hash(doc["text"]), score=0.9, evidence_id=item.id,
                    ))
                return results[:top_k]

            with patch(
                "reasoning_agent_template.workflow.ExternalEvidenceSearch.retrieve",
                autospec=True,
                side_effect=retrieve,
            ):
                payload = orchestrator.run("Compare FlowRelay 2.1 and 2.2 with evidence.", thread_id="case-one")
            saved = sessions.load_messages("case-one")
            return payload, saved, client.calls

    def test_supported_review_with_bound_citation_releases_draft(self):
        draft = "FlowRelay 2.2 deduplication requires enabling the option and supplying a request ID."
        payload, saved, calls = self._run("supported", draft)
        self.assertEqual(payload["gates"]["decisions"][-1]["status"], "allow")
        self.assertEqual(payload["answer"], draft)
        self.assertEqual(payload["output_release"]["status"], "released_model_reviewed")
        self.assertEqual(payload["output_review"]["checked_claims"], 1)
        self.assertEqual(calls, ["coordinator", "route_reviewer", "worker", "output_reviewer"])
        self.assertEqual(saved[-1]["content"], draft)

    def test_issue_or_bad_review_withholds_worker_draft_from_response_and_session(self):
        draft = "UNVERIFIED: deduplication is enabled by default without a request ID."
        for mode in ("issue", "invalid_json", "forged_id", "timeout"):
            with self.subTest(mode=mode):
                payload, saved, calls = self._run(mode, draft)
                self.assertEqual(payload["output_release"]["status"], "withheld")
                self.assertNotIn("UNVERIFIED", json.dumps(payload, ensure_ascii=False))
                self.assertNotIn("UNVERIFIED", json.dumps(saved, ensure_ascii=False))
                self.assertIn("output_reviewer", calls)


if __name__ == "__main__":
    unittest.main()
