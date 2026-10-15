import json
from pathlib import Path
import shutil
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from reasoning_agent_template.learning import BudgetedQwenClient, LearningAssistant
from reasoning_agent_template.llm import ChatResult, LLMRequestError
from tests.test_learning_mvp import CORPUS, ReviewedLearningClient, ScriptedLearningClient


QUESTION = "什么是哈希冲突？"


class GuidedReviewClient(ReviewedLearningClient):
    def __init__(self, mode="supported"):
        super().__init__()
        self.mode = mode
        self.review_attempts = 0
        self.on_review = None

    def chat(self, messages, **kwargs):
        if "OUTPUT_REVIEW_JSON" not in messages[0].content:
            return super().chat(messages, **kwargs)
        self.review_attempts += 1
        if self.on_review:
            self.on_review(json.loads(messages[-1].content))
        if self.mode in {"403", "503", "503_then_success"}:
            if self.mode != "503_then_success" or self.review_attempts == 1:
                self.calls.append("output_reviewer")
                status = 403 if self.mode == "403" else 503
                raise LLMRequestError("PRIVATE_PROVIDER_BODY", status_code=status, retryable=status == 503)
        result = super().chat(messages, **kwargs)
        if self.mode == "bad_json":
            return ChatResult("PRIVATE_RAW_REVIEW", self.model, {})
        review = json.loads(result.content)
        if self.mode == "bad_object":
            review = []
        elif self.mode in {"issue", "uncertain"}:
            review["review_status"] = self.mode
            review["findings"] = ["需要进一步核对"]
        elif self.mode == "missing_coverage":
            review.pop("coverage")
        elif self.mode == "missing_point":
            review["coverage"].pop()
        elif self.mode == "unsupported_point":
            review["coverage"][0]["status"] = "unsupported"
        elif self.mode == "fabricated_excerpt":
            review["coverage"][0]["draft_excerpt"] = "PRIVATE_FAKE_EXCERPT"
        elif self.mode == "repeated_excerpt":
            review["coverage"][1]["draft_excerpt"] = review["coverage"][0]["draft_excerpt"]
        elif self.mode == "stale_receipt":
            review["review_context_hash"] = "a-different-draft"
        elif self.mode == "forged_id":
            review["claims"][0]["evidence_id"] = "ev_not_in_this_run"
        elif self.mode == "source_excerpt":
            review["claims"][0]["excerpt"] = "PRIVATE_FAKE_SOURCE"
        elif self.mode == "empty_claims":
            review["claims"] = []
        return ChatResult(json.dumps(review, ensure_ascii=False), self.model, {})


class LearningGuidedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(CORPUS, self.root / "knowledge")

    def tearDown(self):
        self.temporary.cleanup()

    def test_supported_concept_is_reviewed_before_publication_and_saved_identically(self):
        client = GuidedReviewClient()
        assistant = LearningAssistant(self.root, client=client)

        def inspect_boundary(request):
            self.assertFalse((self.root / "sessions" / "normal" / "snapshot.json").exists())
            active = assistant.orchestrator._active_run
            self.assertEqual(active["working_hint"]["phase"], "output_review")
            self.assertNotIn(request["draft"], json.dumps(active, ensure_ascii=False))
            self.assertEqual([point["id"] for point in request["coverage_requirements"]],
                             ["direct_answer", "reasoning"])

        client.on_review = inspect_boundary
        result = assistant.ask(QUESTION, thread_id="normal")
        self.assertEqual(result["learning"]["path"], "guided")
        self.assertEqual(result["learning"]["decision"], "answered")
        self.assertEqual(result["output_release"]["status"], "released_model_reviewed")
        self.assertIn("两个不同的键", result["answer"])
        self.assertEqual(client.calls, ["route", "reviewer", "worker", "output_reviewer"])
        self.assertEqual(assistant.orchestrator.session_store.load_messages("normal")[-1]["content"],
                         result["answer"])
        self.assertEqual(len([event for event in result["events"] if event["kind"] == "output_review_model"]), 1)

    def test_original_generic_drafts_are_now_withheld_even_with_supported_label(self):
        for index, question in enumerate((QUESTION, "二叉树是什么？", "哈希表和二叉搜索树有什么区别？")):
            with self.subTest(question=question):
                client = ScriptedLearningClient()
                assistant = LearningAssistant(self.root, client=client)
                result = assistant.ask(question, thread_id=f"generic-{index}")
                self.assertEqual(result["learning"]["path"], "guided")
                self.assertEqual(result["learning"]["decision"], "review_withheld")
                self.assertEqual(result["output_release"]["reason"], "answer_coverage_contract_failed")
                self.assertNotIn("结论取决于问题条件", json.dumps(result, ensure_ascii=False))
                self.assertNotIn("结论取决于问题条件", json.dumps(
                    assistant.orchestrator.session_store.load_messages(f"generic-{index}"), ensure_ascii=False))
                self.assertEqual(client.calls, ["route", "reviewer", "worker", "output_reviewer"])

    def test_invalid_reviews_withhold_draft_and_do_not_expose_private_receipt(self):
        for mode in ("issue", "uncertain", "bad_json", "bad_object", "missing_coverage", "missing_point",
                     "unsupported_point", "fabricated_excerpt", "repeated_excerpt", "stale_receipt",
                     "forged_id", "source_excerpt", "empty_claims"):
            with self.subTest(mode=mode):
                client = GuidedReviewClient(mode)
                assistant = LearningAssistant(self.root, client=client)
                result = assistant.ask(QUESTION, thread_id=mode)
                saved = assistant.orchestrator.session_store.load_messages(mode)
                self.assertEqual(result["learning"]["decision"], "review_withheld")
                self.assertEqual(result["output_release"]["status"], "withheld")
                self.assertEqual(saved[-1]["content"], result["answer"])
                self.assertNotIn("哈希冲突是两个不同的键", json.dumps(result, ensure_ascii=False))
                self.assertNotIn("哈希冲突是两个不同的键", json.dumps(saved, ensure_ascii=False))
                self.assertNotIn("PRIVATE_", json.dumps(result, ensure_ascii=False))
                self.assertEqual(client.review_attempts, 1)

    def test_changed_source_chunk_hash_cannot_pass_final_citation_audit(self):
        client = GuidedReviewClient()
        assistant = LearningAssistant(self.root, client=client)
        original = assistant.orchestrator._review_output_answer

        def corrupt_hash(question, draft, state):
            state.retrieval_results = [replace(chunk, content_hash="wrong-content-hash")
                                       for chunk in state.retrieval_results]
            return original(question, draft, state)

        with patch.object(assistant.orchestrator, "_review_output_answer", side_effect=corrupt_hash):
            result = assistant.ask(QUESTION)
        self.assertEqual(result["output_release"]["reason"], "citation_audit_failed")
        self.assertEqual(result["learning"]["decision"], "review_withheld")

    def test_review_transport_failure_is_bounded_and_draft_is_withheld(self):
        for mode, attempts in (("403", 1), ("503", 2)):
            with self.subTest(mode=mode):
                client = GuidedReviewClient(mode)
                result = LearningAssistant(self.root, client=client).ask(QUESTION, thread_id=mode)
                self.assertEqual(client.review_attempts, attempts)
                self.assertEqual(result["learning"]["decision"], "review_withheld")
                self.assertNotIn("PRIVATE_", json.dumps(result, ensure_ascii=False))

    def test_successful_review_retry_has_safe_events_and_one_extra_attempt(self):
        client = GuidedReviewClient("503_then_success")
        result = LearningAssistant(self.root, client=client).ask(QUESTION)
        self.assertEqual(result["learning"]["decision"], "answered")
        self.assertEqual(client.review_attempts, 2)
        self.assertEqual(len(client.calls), 5)
        self.assertFalse("PRIVATE_PROVIDER_BODY" in json.dumps(result, ensure_ascii=False))

    def test_budget_exhaustion_before_review_withholds_generated_answer(self):
        backend = GuidedReviewClient()
        client = BudgetedQwenClient(backend, self.root / "local_state" / "fake_usage.sqlite3", limit=3)
        result = LearningAssistant(self.root, client=client).ask(QUESTION)
        self.assertEqual(client.calls_used(), 3)
        self.assertEqual(backend.calls, ["route", "reviewer", "worker"])
        self.assertEqual(result["learning"]["decision"], "review_withheld")
        self.assertNotIn("哈希冲突是两个不同的键", result["answer"])

    def test_deterministic_stops_skip_worker_and_final_model_review(self):
        for index, question in enumerate(("请解释 ZxqvPrime-99 的内部缓存协议。",
                                           "满二叉树和完全二叉树的定义有什么区别？", "请删除生产环境数据。")):
            with self.subTest(question=question):
                client = GuidedReviewClient()
                result = LearningAssistant(self.root, client=client).ask(question, thread_id=f"stop-{index}")
                self.assertEqual(result["runtime"]["llm"]["status"], "skipped")
                self.assertEqual(result["output_review"]["status"], "not_run")
                self.assertEqual(client.calls, ["route", "reviewer"])

    def test_runtime_flag_cannot_disable_learning_generated_answer_review(self):
        client = GuidedReviewClient()
        assistant = LearningAssistant(self.root, client=client)
        assistant.config.runtime["output_review_enabled"] = False
        result = assistant.ask(QUESTION)
        self.assertEqual(result["output_release"]["status"], "released_model_reviewed")
        self.assertIn("output_reviewer", client.calls)

    def test_structurally_valid_but_wrong_model_support_is_not_a_truth_guarantee(self):
        wrong = "哈希冲突表示不同的键永远不会映射到相同槽位。哈希表因此完全不需要冲突处理。"

        class BlindReviewer(GuidedReviewClient):
            def chat(self, messages, **kwargs):
                result = super().chat(messages, **kwargs)
                if self.calls[-1] == "worker":
                    return ChatResult(wrong, self.model, {})
                return result

        result = LearningAssistant(self.root, client=BlindReviewer()).ask(QUESTION)
        # Intentional limitation: a blind supported judgment can still be wrong.
        self.assertEqual(result["answer"], wrong)
        self.assertEqual(result["output_release"]["status"], "released_model_reviewed")


if __name__ == "__main__":
    unittest.main()
