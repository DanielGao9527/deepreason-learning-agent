import json
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from reasoning_agent_template.learning import (
    BudgetedQwenClient,
    LearningAssistant,
    QwenCallLimitError,
    interactive_session,
    timing_breakdown,
)
from reasoning_agent_template.llm import ChatResult
from reasoning_agent_template.workflow import TemplateCoordinator, WorkflowContractError


CORPUS = Path(__file__).resolve().parents[1] / "learning_mvp" / "knowledge"


class ScriptedLearningClient:
    model = "offline-script"

    def __init__(self, *, final_review: str = "supported"):
        self.calls = []
        self.final_review = final_review

    def chat(self, messages, *, temperature, max_tokens):
        prompt = "\n".join(message.content for message in messages)
        if "ROUTING_DECISION_JSON" in prompt:
            self.calls.append("route")
            question = prompt.split("用户输入:\n", 1)[-1].split("\n\n短期记忆 JSON:", 1)[0]
            deep = "一定" in question
            content = json.dumps({
                "difficulty": "hard" if deep else "simple",
                "workflow": "evidence_strict" if deep else "routine",
                "evidence_mode": "required" if deep else "optional",
                "evidence_strictness": "strict" if deep else "none",
                "risk_level": "high" if deep else "low",
                "category": "hard_reasoning" if deep else "routine",
                "sources": ["web", "papers"],
                "confidence": 0.8,
            }, ensure_ascii=False)
        elif "REVIEW_DECISION_JSON" in prompt:
            self.calls.append("reviewer")
            content = json.dumps({"review_status": "approve", "findings": []})
        elif "OUTPUT_REVIEW_JSON" in prompt:
            self.calls.append("output_reviewer")
            request = json.loads(messages[-1].content)
            source = request["qualified_sources"][0]
            content = json.dumps({
                "review_status": self.final_review,
                "coverage_complete": self.final_review == "supported",
                "findings": [] if self.final_review == "supported" else ["证据与结论需要复核"],
                "claims": [{
                    "claim_id": "demo-claim", "statement": request["draft"],
                    "evidence_id": source["evidence_id"], "excerpt": source["text"][:24],
                }],
            }, ensure_ascii=False)
        else:
            self.calls.append("worker")
            content = "结论取决于问题条件。请回顾资料后自己判断精确查找与范围查询的差别。"
        return ChatResult(content=content, model=self.model, raw={"offline": True})


class LearningMvpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(CORPUS, self.root / "knowledge")

    def tearDown(self):
        self.temp.cleanup()

    def test_concept_question_uses_local_evidence_and_guided_path(self):
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？", thread_id="learner-a")

        self.assertEqual(answer["learning"]["path"], "guided")
        self.assertEqual(answer["evidence"]["mode"], "required")
        self.assertEqual(answer["gates"]["decisions"][-1]["status"], "allow")
        self.assertTrue(answer["learning"]["sources"], f"evidence={answer['evidence']} rag={answer['rag']}")
        self.assertTrue(answer["learning"]["sources"][0]["original_url"].startswith("https://opendsa.cs.vt.edu/"))
        self.assertIn("retrieve", answer["state_machine"]["trace"])
        self.assertEqual(answer["external_evidence"]["attempted_sources"], [])
        self.assertEqual(answer["output_release"]["status"], "released_gate_only")
        self.assertEqual(client.calls, ["route", "reviewer", "worker"])

    def test_conditional_question_uses_strict_path_and_two_local_sources(self):
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask(
            "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。",
            thread_id="learner-b",
        )

        self.assertEqual(answer["learning"]["path"], "deep")
        self.assertEqual(answer["evidence"]["strictness"], "strict")
        self.assertEqual(answer["gates"]["decisions"][-1]["status"], "allow")
        self.assertGreaterEqual(len(answer["evidence"]["qualified_evidence_ids"]), 2)
        self.assertEqual(answer["external_evidence"]["attempted_sources"], [])
        self.assertEqual(answer["output_release"]["status"], "released_model_reviewed")
        self.assertEqual(answer["learning"]["decision"], "answered")
        self.assertEqual(client.calls, ["route", "reviewer", "worker", "output_reviewer"])

    def test_simple_protected_request_keeps_high_risk_despite_weak_model_route(self):
        client = ScriptedLearningClient()  # Deliberately returns routine/low/none.
        assistant = LearningAssistant(self.root, client=client)
        answer = assistant.ask("请删除生产环境数据。", thread_id="protected-route")

        self.assertEqual(answer["routing"]["difficulty"], "simple")
        self.assertEqual(answer["routing"]["workflow"], "protected_action")
        self.assertEqual(answer["routing"]["decision"]["learning_risk_floor"]["category"], "high_risk_action")
        self.assertEqual(answer["evidence"]["risk_level"], "high")
        self.assertEqual(answer["evidence"]["strictness"], "strict")
        self.assertEqual(answer["gates"]["decisions"][-1]["status"], "deny")
        self.assertEqual(answer["output_release"]["status"], "withheld")
        self.assertEqual(client.calls, ["route", "reviewer"])
        saved = assistant.orchestrator.session_store.load("protected-route")
        self.assertEqual(saved.messages[-1]["content"], answer["answer"])
        self.assertTrue(any(event["kind"] == "output_release_decision" for event in saved.events))

    def test_strict_answer_is_withheld_when_independent_review_reports_an_issue(self):
        client = ScriptedLearningClient(final_review="issue")
        answer = LearningAssistant(self.root, client=client).ask(
            "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。",
            thread_id="learner-review",
        )
        self.assertEqual(answer["learning"]["decision"], "review_withheld")
        self.assertEqual(answer["output_release"]["status"], "withheld")
        self.assertNotIn("结论取决于", answer["answer"])
        self.assertEqual(client.calls, ["route", "reviewer", "worker", "output_reviewer"])
        kinds = [event["kind"] for event in answer["events"]]
        self.assertLess(kinds.index("output_review_decision"), kinds.index("output_release_decision"))
        saved = LearningAssistant(self.root, client=client).orchestrator.session_store.load("learner-review")
        self.assertEqual(saved.messages[-1]["content"], answer["answer"])
        self.assertNotIn("结论取决于", json.dumps(saved.to_dict(), ensure_ascii=False))
        self.assertTrue(any(event["kind"] == "output_release_decision" for event in saved.events))

    def test_missing_material_skips_worker_and_does_not_publish_a_guess(self):
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask(
            "请解释 ZxqvPrime-99 的内部缓存协议。", thread_id="learner-c"
        )

        self.assertEqual(answer["runtime"]["llm"]["status"], "skipped")
        self.assertEqual(client.calls, ["route", "reviewer"])
        self.assertNotIn("结论取决于", answer["answer"])
        self.assertTrue("资料" in answer["answer"] or "证据" in answer["answer"])

    def test_new_binary_tree_definition_can_reach_worker(self):
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask("二叉树是什么？", thread_id="binary-definition")

        self.assertEqual(answer["learning"]["decision"], "answered")
        self.assertIn("worker", client.calls)
        self.assertTrue(any("07_binary_tree_definition.md" in source["uri"]
                            for source in answer["learning"]["sources"]))

    def test_retrieval_handoff_is_validated_before_reason_and_worker(self):
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？", thread_id="handoff-valid")

        handoffs = [event for event in answer["events"] if event.get("kind") == "handoff_validated"]
        self.assertEqual(len(handoffs), 1)
        self.assertEqual(handoffs[0]["edge_id"], "retrieve_to_reason")
        self.assertGreater(handoffs[0]["candidate_count"], 0)
        self.assertTrue(handoffs[0]["handoff_hash"])
        self.assertIn("worker", client.calls)

    def test_empty_retrieval_is_valid_handoff_but_cannot_generate_answer(self):
        for path in (self.root / "knowledge").iterdir():
            path.unlink()
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？", thread_id="handoff-empty")

        handoffs = [event for event in answer["events"] if event.get("kind") == "handoff_validated"]
        self.assertEqual(handoffs[0]["candidate_count"], 0)
        self.assertEqual(answer["learning"]["decision"], "abstained_no_evidence")
        self.assertEqual(client.calls, ["route", "reviewer"])

    def test_bad_retrieval_handoff_stops_before_worker_and_session_save(self):
        original_retrieve = TemplateCoordinator._retrieve
        for fault, expected in (
            ("missing_id", "evidence_missing"),
            ("bad_hash", "candidate_hash_mismatch"),
            ("changed_source", "source_changed"),
            ("bad_type", "invalid_candidate_type"),
        ):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(CORPUS, root / "knowledge")
                client = ScriptedLearningClient()

                def faulty_retrieve(coordinator, state):
                    original_retrieve(coordinator, state)
                    self.assertTrue(state.retrieval_results)
                    first = state.retrieval_results[0]
                    if fault == "missing_id":
                        state.retrieval_results[0] = replace(first, evidence_id="ev_missing")
                    elif fault == "bad_hash":
                        state.retrieval_results[0] = replace(first, content_hash="0" * 64)
                    elif fault == "changed_source":
                        source = Path(first.source)
                        source.write_text(source.read_text(encoding="utf-8").replace("哈希", "散列"), encoding="utf-8")
                    else:
                        state.retrieval_results[0] = {"source": first.source}

                with patch.object(TemplateCoordinator, "_retrieve", faulty_retrieve):
                    assistant = LearningAssistant(root, client=client)
                    with self.assertRaises(WorkflowContractError) as caught:
                        assistant.ask("什么是哈希冲突？", thread_id="handoff-failed")
                self.assertEqual(caught.exception.code, expected)
                self.assertEqual(client.calls, ["route", "reviewer"])
                self.assertFalse((root / "sessions" / "handoff-failed" / "snapshot.json").exists())

    def test_general_binary_definition_cannot_answer_two_special_shape_definitions(self):
        questions = (
            "满二叉树和完全二叉树的定义有什么区别？",
            "满二叉树和完全二叉树有啥区别？",
            "请解释满二叉树与完全二叉树有何不同？",
        )
        for index, question in enumerate(questions):
            with self.subTest(question=question):
                client = ScriptedLearningClient()
                answer = LearningAssistant(self.root, client=client).ask(
                    question, thread_id=f"shape-comparison-{index}"
                )

                self.assertIn(answer["learning"]["decision"],
                              {"abstained_incomplete_evidence", "abstained_no_evidence"})
                self.assertIn(answer["runtime"]["llm"]["reason"],
                              {"missing_comparison_subjects", "no_qualified_local_evidence"})
                if index == 0:
                    self.assertEqual(answer["runtime"]["llm"]["reason"], "missing_comparison_subjects")
                self.assertEqual(client.calls, ["route", "reviewer"])
                self.assertEqual(answer["learning"]["sources"], [])
                self.assertNotIn("结论取决于", answer["answer"])

    def test_definition_comparison_reaches_worker_when_both_subjects_are_in_material(self):
        (self.root / "knowledge" / "08_shape_definitions_test_only.md").write_text(
            "满二叉树：每个内部结点恰有两个非空孩子。"
            "完全二叉树：除末层外各层填满，末层从左向右填充。",
            encoding="utf-8",
        )
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask(
            "满二叉树和完全二叉树的定义有什么区别？", thread_id="shape-covered"
        )

        self.assertEqual(answer["learning"]["decision"], "answered")
        self.assertIn("worker", client.calls)

    def test_call_limit_persists_and_counts_attempts_before_send(self):
        class Client:
            model = "offline-script"
            calls = 0

            def chat(self, messages, *, temperature, max_tokens):
                self.calls += 1
                return ChatResult(content="ok", model=self.model, raw={})

        backend = Client()
        usage_db = self.root / "local_state" / "usage.sqlite3"
        first = BudgetedQwenClient(backend, usage_db, limit=2)
        self.assertEqual(BudgetedQwenClient(backend, usage_db, limit=999).limit, 100)
        first.chat([], temperature=0, max_tokens=10)
        second = BudgetedQwenClient(backend, usage_db, limit=2)
        second.chat([], temperature=0, max_tokens=10)
        with self.assertRaises(QwenCallLimitError):
            second.chat([], temperature=0, max_tokens=10)
        self.assertEqual(backend.calls, 2)
        self.assertEqual(first.calls_used(), 2)

    def test_same_thread_restores_recent_turns_after_restart_without_cross_thread_leak(self):
        client = ScriptedLearningClient()
        first = LearningAssistant(self.root, client=client)
        first.ask("什么是哈希冲突？", thread_id="learner-a")

        restarted = LearningAssistant(self.root, client=client)
        continuation = restarted.ask("哈希冲突怎么处理？", thread_id="learner-a")
        other_thread = restarted.ask("什么是哈希冲突？", thread_id="learner-b")

        self.assertEqual(continuation["memory"]["short_term"]["turns"], 2)
        self.assertEqual(other_thread["memory"]["short_term"]["turns"], 1)
        self.assertEqual(other_thread["memory"]["long_term"]["records"], 0)

    def test_learning_request_does_not_turn_a_question_into_permanent_profile(self):
        client = ScriptedLearningClient()
        answer = LearningAssistant(self.root, client=client).ask(
            "记住我不懂哈希冲突，什么是哈希冲突？", thread_id="learner-a"
        )
        self.assertEqual(answer["memory"]["long_term"]["records"], 0)
        self.assertFalse((self.root / "memory" / "user.jsonl").exists())

    def test_interactive_session_answers_and_keeps_one_thread(self):
        client = ScriptedLearningClient()
        assistant = LearningAssistant(self.root, client=client)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["什么是哈希冲突？", "哈希冲突怎么处理？", "/exit"]), redirect_stdout(output):
            status = interactive_session(assistant, thread_id="same-thread")
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue().count("路径：guided"), 2)
        self.assertEqual(output.getvalue().count("耗时："), 2)
        messages = assistant.orchestrator.session_store.load_messages("same-thread")
        self.assertEqual([item["role"] for item in messages], ["user", "assistant", "user", "assistant"])

    def test_timing_breakdown_shows_serial_model_calls_and_local_retrieval(self):
        client = ScriptedLearningClient()
        guided = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？", thread_id="timing-guided")
        guided_labels = dict(timing_breakdown(guided))
        self.assertTrue({"总计", "路由", "路线复核", "本地检索", "回答生成"} <= guided_labels.keys())
        self.assertNotIn("答案复核", guided_labels)
        deep = LearningAssistant(self.root, client=client).ask(
            "哈希表一定比二叉搜索树快吗？比较精确查找和范围查询。", thread_id="timing-deep"
        )
        self.assertIn("答案复核", dict(timing_breakdown(deep)))


if __name__ == "__main__":
    unittest.main()
