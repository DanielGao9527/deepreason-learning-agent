import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reasoning_agent_template.config import AgentConfig
from reasoning_agent_template.llm import ChatResult
from reasoning_agent_template.models import GateDecision
from reasoning_agent_template.multiagent import MultiAgentOrchestrator
from reasoning_agent_template.release_policy import decide_release
from reasoning_agent_template.sessions import SessionStore


class ScriptedClient:
    model = "offline-script"

    def __init__(self, route, draft):
        self.route = route
        self.draft = draft
        self.calls = 0

    def chat(self, messages, *, temperature, max_tokens):
        self.calls += 1
        prompt = "\n".join(message.content for message in messages)
        if "ROUTING_DECISION_JSON" in prompt:
            content = json.dumps(self.route)
        elif "REVIEW_DECISION_JSON" in prompt:
            content = json.dumps({"review_status": "approve", "findings": []})
        else:
            content = self.draft
        return ChatResult(content=content, model=self.model, raw={"scripted": True})


class ReleasePolicyTests(unittest.TestCase):
    def test_policy_withholds_without_allow(self):
        draft = "UNVERIFIED_CLAIM"
        for gate_status in ("interrupt", "deny"):
            gate = GateDecision(gate_id="gate-test", risk_level="high", status=gate_status, reasons=[])
            with self.subTest(gate_status=gate_status):
                result = decide_release(draft, [gate])
                self.assertEqual(result.status, "withheld")
                self.assertNotIn(draft, result.answer)
        self.assertTrue(decide_release(draft, []).draft_withheld)
        allowed = GateDecision(gate_id="gate-allow", risk_level="low", status="allow", reasons=[])
        result = decide_release(draft, [allowed])
        self.assertEqual(result.answer, draft)
        self.assertEqual(result.status, "released_gate_only")

    def test_worker_draft_cannot_reach_response_or_session_after_interrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "knowledge").mkdir()
            config = AgentConfig.default(workspace_root=root)
            config.knowledge["directory"] = str(root / "knowledge")
            sessions = SessionStore(root / "sessions")
            client = ScriptedClient(
                route={
                    "source": "scripted",
                    "difficulty": "hard",
                    "workflow": "evidence_strict",
                    "evidence_mode": "required",
                    "evidence_strictness": "strict",
                    "risk_level": "high",
                    "category": "hard_reasoning",
                    "sources": ["rag", "papers"],
                    "reasons": ["requires evidence"],
                    "confidence": 0.8,
                },
                draft="UNVERIFIED_CLAIM: choose version A with certainty.",
            )
            orchestrator = MultiAgentOrchestrator(
                config=config,
                workspace_root=root,
                llm_client_factory=lambda _config: client,
                session_store=sessions,
            )
            with patch(
                "reasoning_agent_template.workflow.ExternalEvidenceSearch.retrieve",
                autospec=True,
                return_value=[],
            ):
                payload = orchestrator.run("Compare two versions and cite reliable evidence.", thread_id="case-one")
            self.assertEqual(payload["gates"]["decisions"][-1]["status"], "interrupt")
            self.assertEqual(payload["output_release"]["status"], "withheld")
            self.assertEqual(client.calls, 3)
            self.assertNotIn("UNVERIFIED_CLAIM", json.dumps(payload, ensure_ascii=False))
            self.assertNotIn("UNVERIFIED_CLAIM", json.dumps(sessions.load_messages("case-one")))

    def test_allowed_routine_draft_is_preserved_and_marked_gate_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "knowledge").mkdir()
            config = AgentConfig.default(workspace_root=root)
            config.knowledge["directory"] = str(root / "knowledge")
            client = ScriptedClient(
                route={
                    "source": "scripted",
                    "difficulty": "simple",
                    "workflow": "routine",
                    "evidence_mode": "optional",
                    "evidence_strictness": "none",
                    "risk_level": "none",
                    "category": "routine",
                    "sources": [],
                    "confidence": 0.8,
                },
                draft="A concise greeting.",
            )
            orchestrator = MultiAgentOrchestrator(
                config=config, workspace_root=root, llm_client_factory=lambda _config: client
            )
            payload = orchestrator.run("Hello")
            self.assertEqual(payload["gates"]["decisions"][-1]["status"], "allow")
            self.assertEqual(payload["answer"], "A concise greeting.")
            self.assertEqual(payload["output_release"]["status"], "released_gate_only")


if __name__ == "__main__":
    unittest.main()
