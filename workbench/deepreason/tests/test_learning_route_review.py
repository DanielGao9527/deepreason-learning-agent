import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from reasoning_agent_template.knowledge import LocalKnowledgeBase
from reasoning_agent_template.learning import (
    BudgetedQwenClient, LearningAssistant, LearningRouteReviewError, interactive_session, main,
)
from reasoning_agent_template.llm import ChatResult, LLMRequestError
from reasoning_agent_template.multiagent import MultiAgentOrchestrator
from tests.test_learning_mvp import CORPUS, ReviewedLearningClient


class RouteReviewClient(ReviewedLearningClient):
    def __init__(self, reply):
        super().__init__()
        self.reply = reply

    def chat(self, messages, **kwargs):
        if messages[-1].content.startswith("REVIEW_DECISION_JSON schema:"):
            self.calls.append("reviewer")
            if isinstance(self.reply, Exception):
                raise self.reply
            content = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
            return ChatResult(content=content, model=self.model, raw={"offline": True})
        return super().chat(messages, **kwargs)


class LearningRouteReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(CORPUS, self.root / "knowledge")

    def tearDown(self):
        self.temporary.cleanup()

    def test_invalid_receipts_stop_before_retrieval_worker_and_session_with_safe_reason(self):
        approve = {"review_status": "approve", "findings": []}
        cases = [
            ("PRIVATE_REVIEW_BODY", "invalid_review_json"),
            ('{"review_status":"approve","findings":[', "invalid_review_json"),
            ('{"review_status":"approve","findings":[],"confidence":' + "9" * 5000 + '}',
             "invalid_review_json"),
            ("{}", "invalid_review_status"),
            ("[]", "invalid_review_object"),
            ("null", "invalid_review_object"),
            ({"review_status": "aprove", "findings": []}, "invalid_review_status"),
            ({"review_status": [], "findings": []}, "invalid_review_status"),
            ({"review_status": "approve"}, "invalid_review_list"),
            ({**approve, "findings": "ok"}, "invalid_review_list"),
            ({**approve, "findings": [{}]}, "invalid_review_list"),
            ({**approve, "findings": [""]}, "invalid_review_list"),
            ({**approve, "findings": ["evidence is missing"]}, "approval_contains_findings"),
            ({**approve, "review_status": "escalate"}, "missing_review_findings"),
            ({**approve, "risk_level": "urgent"}, "invalid_review_route_field"),
            ({**approve, "difficulty": []}, "invalid_review_route_field"),
            ({**approve, "evidence_mode": True}, "invalid_review_route_field"),
            ({**approve, "evidence_strictness": "relaxed"}, "invalid_review_route_field"),
            ({**approve, "workflow": "run_shell"}, "invalid_review_route_field"),
            ({**approve, "category": "anything"}, "invalid_review_route_field"),
            ({**approve, "sources": ["unknown-provider"]}, "invalid_review_source"),
            ({**approve, "sources": [{}]}, "invalid_review_list"),
            ({**approve, "reasons": None}, "invalid_review_list"),
            ({**approve, "retrieval_query": []}, "invalid_review_query"),
            ({**approve, "confidence": True}, "invalid_review_number"),
            ({**approve, "confidence": 1.1}, "invalid_review_number"),
            ({**approve, "confidence": 10 ** 400}, "invalid_review_number"),
            ('{"review_status":"approve","findings":[],"confidence":NaN}', "invalid_review_number"),
            ('{"review_status":"approve","findings":[],"confidence":1e999}', "invalid_review_number"),
            ({**approve, "private_field": "PRIVATE_REVIEW_BODY"}, "unknown_review_field"),
            ('{"review_status":"escalate","review_status":"approve","findings":[]}',
             "duplicate_review_field"),
            ('{"review_status":"approve","findings":[]} {"review_status":"approve"}',
             "invalid_review_json"),
        ]
        for index, (reply, code) in enumerate(cases):
            with self.subTest(index=index, code=code):
                workspace = self.root / str(index)
                backend = RouteReviewClient(reply)
                usage = workspace / "local_state" / "fake_usage.sqlite3"
                client = BudgetedQwenClient(backend, usage)
                assistant = LearningAssistant(workspace, client=client)
                with patch.object(LocalKnowledgeBase, "retrieve", side_effect=AssertionError("must not retrieve")):
                    with self.assertRaises(LearningRouteReviewError) as raised:
                        assistant.ask("PRIVATE_QUESTION 什么是哈希冲突？", thread_id="PRIVATE_THREAD")
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(backend.calls, ["route", "reviewer"])
                self.assertEqual(BudgetedQwenClient.calls_used_at(usage), 2)
                self.assertFalse((workspace / "sessions" / "PRIVATE_THREAD" / "snapshot.json").exists())
                paths = list((workspace / "local_state" / "failures").glob("*.json"))
                self.assertEqual(len(paths), 1)
                raw = paths[0].read_text(encoding="utf-8")
                trace = json.loads(raw)
                self.assertEqual(trace["terminal_status"], "route_review_failed")
                self.assertEqual(trace["reason_code"], code)
                self.assertEqual(trace["phase"], "route_review")
                self.assertFalse(trace["session_saved"])
                self.assertNotIn("PRIVATE_", raw)
                self.assertNotIn("PRIVATE_", str(raised.exception))

    def test_valid_approval_json_and_single_fenced_object_keep_guided_path(self):
        for reply in ('{"review_status":"approve","findings":[]}',
                      '```json\n{"review_status":"approve","findings":[]}\n```'):
            with self.subTest(reply=reply):
                client = RouteReviewClient(reply)
                answer = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？")
                self.assertEqual(answer["reviewer"]["status"], "approve")
                self.assertEqual(answer["learning"]["decision"], "answered")
                self.assertEqual(answer["learning"]["path"], "guided")
                self.assertEqual(client.calls, ["route", "reviewer", "worker", "output_reviewer"])

    def test_valid_review_escalation_and_revision_really_upgrade_before_workflow(self):
        for status in ("escalate", "revise"):
            with self.subTest(status=status):
                client = RouteReviewClient({
                    "review_status": status, "findings": ["需要严格审查结论"],
                    "difficulty": "hard", "evidence_strictness": "strict",
                    "risk_level": "high", "confidence": 0.8,
                })
                answer = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？", thread_id=status)
                self.assertEqual(answer["reviewer"]["status"], status)
                self.assertEqual(answer["routing"]["difficulty"], "hard")
                self.assertEqual(answer["evidence"]["strictness"], "strict")
                self.assertEqual(answer["learning"]["path"], "deep")
                # This concept fixture has a complete answer and coverage receipt.
                self.assertEqual(answer["learning"]["decision"], "answered")
                self.assertEqual(client.calls, ["route", "reviewer", "worker", "output_reviewer"])

    def test_noop_or_weaker_revision_cannot_count_as_a_completed_review(self):
        cases = [
            {"review_status": "revise", "findings": ["请补充依据"]},
            {"review_status": "escalate", "findings": ["建议升级"],
             "risk_level": "low", "difficulty": "simple", "evidence_strictness": "none"},
        ]
        for index, reply in enumerate(cases):
            with self.subTest(index=index):
                client = RouteReviewClient(reply)
                assistant = LearningAssistant(self.root, client=client)
                with self.assertRaises(LearningRouteReviewError) as raised:
                    assistant.ask("什么是哈希冲突？", thread_id=f"no-change-{index}")
                self.assertEqual(raised.exception.code, "review_change_not_applied")
                self.assertEqual(client.calls, ["route", "reviewer"])

    def test_approval_cannot_downgrade_an_already_strict_route(self):
        client = RouteReviewClient({"review_status": "approve", "findings": [],
                                    "difficulty": "simple", "evidence_mode": "optional",
                                    "evidence_strictness": "none", "risk_level": "low"})
        answer = LearningAssistant(self.root, client=client).ask(
            "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。")
        self.assertEqual(answer["routing"]["difficulty"], "hard")
        self.assertEqual(answer["evidence"]["strictness"], "strict")
        self.assertEqual(answer["learning"]["decision"], "review_withheld")

    def test_bad_review_preserves_existing_history_then_same_instance_can_retry(self):
        client = RouteReviewClient({"review_status": "approve", "findings": []})
        assistant = LearningAssistant(self.root, client=client)
        assistant.ask("什么是哈希冲突？第一轮。", thread_id="history")
        snapshot = self.root / "sessions" / "history" / "snapshot.json"
        original = snapshot.read_bytes()
        client.reply = "{}"
        with self.assertRaises(LearningRouteReviewError):
            assistant.ask("什么是哈希冲突？失败轮。", thread_id="history")
        self.assertEqual(snapshot.read_bytes(), original)
        client.reply = {"review_status": "approve", "findings": []}
        assistant.ask("什么是哈希冲突？第三轮。", thread_id="history")
        users = [m["content"] for m in assistant.orchestrator.session_store.load_messages("history")
                 if m["role"] == "user"]
        self.assertEqual(users, ["什么是哈希冲突？第一轮。", "什么是哈希冲突？第三轮。"])

    def test_transport_failure_keeps_bounded_retry_and_separate_failure_status(self):
        for status, retryable, expected_attempts in ((403, False, 1), (503, True, 2)):
            with self.subTest(status=status):
                workspace = self.root / str(status)
                client = RouteReviewClient(LLMRequestError("controlled model error", status_code=status,
                                                          retryable=retryable))
                assistant = LearningAssistant(workspace, client=client)
                with self.assertRaises(LLMRequestError):
                    assistant.ask("什么是哈希冲突？")
                self.assertEqual(client.calls, ["route"] + ["reviewer"] * expected_attempts)
                trace = json.loads(next((workspace / "local_state" / "failures").glob("*.json"))
                                   .read_text(encoding="utf-8"))
                self.assertEqual(trace["terminal_status"], "model_unavailable")
                self.assertEqual(trace["http_status"], status)

    def test_cli_and_interactive_report_invalid_review_without_raw_body_or_traceback(self):
        client = RouteReviewClient("PRIVATE_REVIEW_BODY")
        errors = io.StringIO()
        with patch("reasoning_agent_template.learning.qwen_client_from_env", return_value=client):
            with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                main(["--workspace", str(self.root), "什么是哈希冲突？"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid_review_json", errors.getvalue())
        self.assertNotIn("PRIVATE_", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())
        output = io.StringIO()
        with redirect_stdout(output), patch("builtins.input", side_effect=["什么是哈希冲突？", "/exit"]):
            self.assertEqual(interactive_session(LearningAssistant(self.root, client=client)), 0)
        self.assertIn("LearningRouteReviewError", output.getvalue())
        self.assertNotIn("PRIVATE_", output.getvalue())

    def test_generic_orchestrator_keeps_upstream_tolerant_parser(self):
        orchestrator = MultiAgentOrchestrator(config=LearningAssistant(self.root).config,
                                             workspace_root=self.root)
        self.assertIsNone(orchestrator._parse_route_review("not json"))
        self.assertEqual(orchestrator._parse_route_review("{}"), {})


if __name__ == "__main__":
    unittest.main()
