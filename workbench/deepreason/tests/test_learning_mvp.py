import json
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from reasoning_agent_template.learning import (
    BudgetedQwenClient,
    LearningAssistant,
    LearningCorpusChangedError,
    LearningOrchestrator,
    LearningRetrievalTimeoutError,
    QwenCallLimitError,
    interactive_session,
    main,
    timing_breakdown,
)
from reasoning_agent_template.learning_plan import LearningPlanError, build_comparison_plan
from reasoning_agent_template.knowledge import LocalKnowledgeBase
from reasoning_agent_template.llm import ChatResult, DeepSeekChatClient, LLMRequestError
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

    def _failure_trace(self, root: Path) -> tuple[dict, str]:
        files = list((root / "local_state" / "failures").glob("*.json"))
        self.assertEqual(len(files), 1)
        raw = files[0].read_text(encoding="utf-8")
        return json.loads(raw), raw

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
        self.assertFalse((self.root / "local_state" / "failures").exists())

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
                trace, raw = self._failure_trace(root)
                self.assertEqual(trace["terminal_status"], "handoff_rejected")
                self.assertEqual(trace["reason_code"], expected)
                self.assertEqual(trace["edge_id"], "retrieve_to_reason")
                self.assertEqual(trace["stage"], "retrieve")
                self.assertFalse(trace["session_saved"])
                self.assertNotIn("什么是哈希冲突", raw)

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
                              {"incomplete_comparison_plan", "no_qualified_local_evidence"})
                if index == 0:
                    self.assertEqual(answer["runtime"]["llm"]["reason"], "incomplete_comparison_plan")
                plan = answer["workflow"]["execution_plan"]
                self.assertEqual(plan["kind"], "two_subject_evidence")
                self.assertEqual(plan["status"], "blocked_missing_subject")
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
        original_retrieve = LocalKnowledgeBase.retrieve
        queries = []
        shared_scores = {}

        def tracked_retrieve(kb, query, **kwargs):
            queries.append(query)
            results = original_retrieve(kb, query, **kwargs)
            for chunk in results:
                if "满二叉树" in chunk.text and "完全二叉树" in chunk.text:
                    shared_scores.setdefault(chunk.evidence_id, []).append(chunk.score)
            return results

        with patch.object(LocalKnowledgeBase, "retrieve", tracked_retrieve):
            answer = LearningAssistant(self.root, client=client).ask(
                "满二叉树和完全二叉树的定义有什么区别？", thread_id="shape-covered"
            )

        self.assertEqual(answer["learning"]["decision"], "answered")
        self.assertIn("worker", client.calls)
        plan = answer["workflow"]["execution_plan"]
        self.assertEqual(plan["status"], "completed")
        self.assertEqual([task["id"] for task in plan["tasks"]],
                         ["lookup_left", "lookup_right", "join_evidence"])
        self.assertTrue(all(task["status"] == "completed" for task in plan["tasks"]))
        self.assertEqual(len([event for event in answer["events"] if event.get("kind") == "plan_task_completed"]), 3)
        self.assertEqual(queries, ["满二叉树", "完全二叉树"])
        self.assertTrue(any(len(scores) == 2 for scores in shared_scores.values()))
        final_scores = {chunk["evidence_id"]: chunk["score"] for chunk in answer["rag"]["results"]}
        for evidence_id, scores in shared_scores.items():
            if len(scores) == 2:
                self.assertEqual(final_scores[evidence_id], max(scores))
        for task in plan["tasks"][:2]:
            self.assertTrue(task["candidate_evidence_ids"])
            self.assertTrue(any(task["subject"] in chunk["text"] for chunk in answer["rag"]["results"]))

    def test_top_k_omission_gets_one_wider_read_without_lowering_score_floor(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            corpus = root / "knowledge"
            corpus.mkdir()
            left = "满二叉树"
            right = "完全二叉树"
            (corpus / "left_definition.md").write_text(
                f"{left}：每个内部结点恰有两个孩子。 "
                + " ".join(f"filler{i}" for i in range(100)), encoding="utf-8",
            )
            (corpus / "right_definition.md").write_text(
                f"{right}：除末层外均填满，末层从左向右填充。", encoding="utf-8",
            )
            for index in range(5):
                (corpus / f"distractor_{index}.md").write_text(
                    f"满 二叉树 {index}", encoding="utf-8",
                )
            calls = []
            original_retrieve = LocalKnowledgeBase.retrieve

            def tracked_retrieve(kb, query, **kwargs):
                results = original_retrieve(kb, query, **kwargs)
                calls.append((query, kwargs["top_k"], kwargs["min_score"],
                              sum(query in item.text for item in results)))
                return results

            client = ScriptedLearningClient()
            with patch.object(LocalKnowledgeBase, "retrieve", tracked_retrieve):
                answer = LearningAssistant(root, client=client).ask(
                    "满二叉树和完全二叉树的定义有什么区别？", thread_id="topk-recovery",
                )
            plan = answer["workflow"]["execution_plan"]
            self.assertEqual(answer["learning"]["decision"], "answered")
            self.assertEqual(plan["status"], "completed")
            self.assertEqual([row[1] for row in calls], [4, 12, 4])
            self.assertEqual([row[3] for row in calls], [0, 1, 1])
            self.assertEqual([row[2] for row in calls], [0.08] * 3)
            self.assertEqual(len(plan["tasks"][0]["retrieval_attempts"]), 2)
            self.assertEqual(len(plan["tasks"][1]["retrieval_attempts"]), 1)
            self.assertEqual(len([event for event in answer["events"]
                                  if event.get("kind") == "retrieval_recovery_attempted"]), 1)
            self.assertEqual(client.calls, ["route", "reviewer", "worker"])

    def test_missing_subject_stops_after_one_wider_read_and_skips_worker(self):
        calls = []
        original_retrieve = LocalKnowledgeBase.retrieve

        def tracked_retrieve(kb, query, **kwargs):
            calls.append((query, kwargs["top_k"]))
            return original_retrieve(kb, query, **kwargs)

        client = ScriptedLearningClient()
        with patch.object(LocalKnowledgeBase, "retrieve", tracked_retrieve):
            answer = LearningAssistant(self.root, client=client).ask(
                "满二叉树和完全二叉树的定义有什么区别？", thread_id="missing-after-retry",
            )
        self.assertEqual(answer["learning"]["decision"], "abstained_incomplete_evidence")
        self.assertEqual(answer["workflow"]["execution_plan"]["status"], "blocked_missing_subject")
        self.assertLessEqual(len(calls), 4)
        self.assertTrue(any(top_k == 12 for _, top_k in calls))
        self.assertEqual(client.calls, ["route", "reviewer"])

    def test_empty_corpus_does_not_waste_the_top_k_recovery_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "knowledge").mkdir()
            client = ScriptedLearningClient()
            calls = []
            original_retrieve = LocalKnowledgeBase.retrieve

            def tracked_retrieve(kb, query, **kwargs):
                calls.append(kwargs["top_k"])
                return original_retrieve(kb, query, **kwargs)

            with patch.object(LocalKnowledgeBase, "retrieve", tracked_retrieve):
                answer = LearningAssistant(root, client=client).ask(
                    "满二叉树和完全二叉树的定义有什么区别？", thread_id="empty-corpus",
                )
            self.assertEqual(calls, [4, 4])
            self.assertEqual(answer["learning"]["decision"], "abstained_incomplete_evidence")
            self.assertEqual(client.calls, ["route", "reviewer"])

    def test_corpus_change_during_retrieval_stops_before_worker_and_session(self):
        client = ScriptedLearningClient()
        original_retrieve = LocalKnowledgeBase.retrieve
        changed = False

        def changing_retrieve(kb, query, **kwargs):
            nonlocal changed
            results = original_retrieve(kb, query, **kwargs)
            if not changed:
                changed = True
                (self.root / "knowledge" / "changed.md").write_text("new premise", encoding="utf-8")
            return results

        with patch.object(LocalKnowledgeBase, "retrieve", changing_retrieve):
            with self.assertRaises(LearningCorpusChangedError):
                LearningAssistant(self.root, client=client).ask(
                    "满二叉树和完全二叉树的定义有什么区别？", thread_id="changed-corpus",
                )
        self.assertEqual(client.calls, ["route", "reviewer"])
        self.assertFalse((self.root / "sessions" / "changed-corpus" / "snapshot.json").exists())
        trace, _ = self._failure_trace(self.root)
        self.assertEqual(trace["terminal_status"], "precondition_changed")
        self.assertEqual(trace["reason_code"], "knowledge_source_changed")

    def test_corpus_change_after_retrieval_stops_before_worker(self):
        (self.root / "knowledge" / "08_shape_definitions_test_only.md").write_text(
            "满二叉树有两个非空孩子。完全二叉树的末层从左向右填充。", encoding="utf-8",
        )
        client = ScriptedLearningClient()
        original_worker = LearningOrchestrator._call_deepseek

        def change_before_worker(orchestrator, message, state, *, short_term_memory, long_term_memory):
            (self.root / "knowledge" / "08_shape_definitions_test_only.md").write_text(
                "满二叉树有两个非空孩子。完全二叉树的末层从右向左填充。", encoding="utf-8",
            )
            return original_worker(orchestrator, message, state,
                                   short_term_memory=short_term_memory, long_term_memory=long_term_memory)

        with patch.object(LearningOrchestrator, "_call_deepseek", change_before_worker):
            with self.assertRaises(LearningCorpusChangedError):
                LearningAssistant(self.root, client=client).ask(
                    "满二叉树和完全二叉树的定义有什么区别？", thread_id="changed-before-worker",
                )
        self.assertEqual(client.calls, ["route", "reviewer"])
        self.assertFalse((self.root / "sessions" / "changed-before-worker" / "snapshot.json").exists())
        self.assertEqual(self._failure_trace(self.root)[0]["terminal_status"], "precondition_changed")

    def test_late_worker_result_is_withheld_if_corpus_changes_while_it_runs(self):
        source = self.root / "knowledge" / "08_shape_definitions_test_only.md"
        source.write_text("满二叉树有两个非空孩子。完全二叉树末层从左向右填充。", encoding="utf-8")

        class ChangingWorker(ScriptedLearningClient):
            def chat(self, messages, *, temperature, max_tokens):
                result = super().chat(messages, temperature=temperature, max_tokens=max_tokens)
                if self.calls[-1] == "worker":
                    source.write_text("满二叉树有两个非空孩子。完全二叉树末层从右向左填充。", encoding="utf-8")
                return result

        client = ChangingWorker()
        with self.assertRaises(LearningCorpusChangedError):
            LearningAssistant(self.root, client=client).ask(
                "满二叉树和完全二叉树的定义有什么区别？", thread_id="late-worker",
            )
        self.assertEqual(client.calls, ["route", "reviewer", "worker"])
        self.assertFalse((self.root / "sessions" / "late-worker" / "snapshot.json").exists())
        trace, raw = self._failure_trace(self.root)
        self.assertEqual(trace["terminal_status"], "precondition_changed")
        self.assertNotIn("结论取决于问题条件", raw)

    def test_retrieval_timeout_does_not_retry_model_or_publish(self):
        client = ScriptedLearningClient()
        calls = []
        original_retrieve = LocalKnowledgeBase.retrieve

        def timeout_on_recovery(kb, query, **kwargs):
            calls.append(kwargs["top_k"])
            if kwargs["top_k"] == 12:
                raise TimeoutError("private provider detail")
            return original_retrieve(kb, query, **kwargs)

        with patch.object(LocalKnowledgeBase, "retrieve", timeout_on_recovery):
            with self.assertRaises(LearningRetrievalTimeoutError):
                LearningAssistant(self.root, client=client).ask(
                    "满二叉树和完全二叉树的定义有什么区别？", thread_id="retrieval-timeout",
                )
        self.assertEqual(calls, [4, 12])
        self.assertEqual(client.calls, ["route", "reviewer"])
        self.assertFalse((self.root / "sessions" / "retrieval-timeout" / "snapshot.json").exists())
        trace, raw = self._failure_trace(self.root)
        self.assertEqual(trace["terminal_status"], "retrieval_unavailable")
        self.assertNotIn("private provider detail", raw)

    def test_invalid_comparison_plan_stops_before_retrieval_and_session_save(self):
        def bad_plan(fault):
            plan = build_comparison_plan("满二叉树", "完全二叉树")
            if fault == "missing_dependency":
                plan["tasks"][2]["depends_on"] = ["not_a_task"]
            elif fault == "cycle":
                plan["tasks"][0]["depends_on"] = ["lookup_right"]
                plan["tasks"][1]["depends_on"] = ["lookup_left"]
            elif fault == "unavailable_handler":
                plan["tasks"][0]["handler"] = "shell"
            elif fault == "retrieval_budget":
                plan["recovery_top_k"] = 1000
            else:
                plan["max_steps"] = 4
            return plan

        for fault, reason in (
            ("missing_dependency", "missing_dependency"),
            ("cycle", "cyclic_dependencies"),
            ("unavailable_handler", "unavailable_handler"),
            ("retrieval_budget", "invalid_retrieval_budget"),
            ("step_budget", "invalid_step_budget"),
        ):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(CORPUS, root / "knowledge")
                client = ScriptedLearningClient()
                with patch("reasoning_agent_template.learning.build_comparison_plan", return_value=bad_plan(fault)):
                    with patch.object(LocalKnowledgeBase, "retrieve") as retrieve:
                        with self.assertRaises(LearningPlanError) as caught:
                            LearningAssistant(root, client=client).ask(
                                "满二叉树和完全二叉树的定义有什么区别？", thread_id="bad-plan"
                            )
                retrieve.assert_not_called()
                self.assertEqual(str(caught.exception), reason)
                self.assertEqual(client.calls, ["route", "reviewer"])
                self.assertFalse((root / "sessions" / "bad-plan" / "snapshot.json").exists())
                trace, raw = self._failure_trace(root)
                self.assertEqual(trace["terminal_status"], "plan_invalid")
                self.assertEqual(trace["reason_code"], reason)
                self.assertEqual(trace["stage"], "plan")
                self.assertFalse(trace["session_saved"])
                self.assertNotIn("满二叉树和完全二叉树", raw)

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

    def test_quota_http_403_stops_after_one_reserved_request(self):
        backend = DeepSeekChatClient(api_key="offline-test-key", base_url="https://example.invalid")
        usage_db = self.root / "local_state" / "qwen_usage.sqlite3"
        assistant = LearningAssistant(self.root, client=BudgetedQwenClient(backend, usage_db))

        def quota_error(req, timeout):
            body = b'{"error":{"code":"AllocationQuota.FreeTierOnly","message":"quota exhausted"}}'
            raise HTTPError(req.full_url, 403, "Forbidden", {}, BytesIO(body))

        with patch("reasoning_agent_template.llm.request.urlopen", side_effect=quota_error) as sent:
            with self.assertRaises(LLMRequestError) as caught:
                assistant.ask("什么是哈希冲突？", thread_id="quota-failure")
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(caught.exception.provider_code, "AllocationQuota.FreeTierOnly")
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(BudgetedQwenClient.calls_used_at(usage_db), 1)
        self.assertFalse((self.root / "sessions" / "quota-failure" / "snapshot.json").exists())
        trace, raw = self._failure_trace(self.root)
        self.assertEqual(trace["terminal_status"], "model_unavailable")
        self.assertEqual(trace["stage"], "intake")
        self.assertEqual(trace["http_status"], 403)
        self.assertFalse(trace["retryable"])
        self.assertNotIn("quota exhausted", raw)

    def test_failure_trace_is_durable_and_redacts_inputs_and_provider_text(self):
        class FailingRoute(ScriptedLearningClient):
            def chat(self, messages, *, temperature, max_tokens):
                raise LLMRequestError(
                    "PRIVATE_ERROR_VALUE", status_code=403, retryable=False,
                    provider_code="PRIVATE_PROVIDER_CODE",
                )

        assistant = LearningAssistant(self.root, client=FailingRoute())
        with self.assertRaises(LLMRequestError):
            assistant.ask("PRIVATE_QUESTION_VALUE", thread_id="PRIVATE_THREAD_VALUE")
        trace, raw = self._failure_trace(self.root)
        self.assertEqual(trace["terminal_status"], "model_unavailable")
        self.assertEqual(trace["http_status"], 403)
        self.assertFalse(trace["session_saved"])
        for secret in ("PRIVATE_ERROR_VALUE", "PRIVATE_PROVIDER_CODE", "PRIVATE_QUESTION_VALUE", "PRIVATE_THREAD_VALUE"):
            self.assertNotIn(secret, raw)
        self.assertFalse((self.root / "sessions" / "PRIVATE_THREAD_VALUE" / "snapshot.json").exists())
        # Failure evidence is a file, not merely the old orchestrator's in-memory status.
        LearningAssistant(self.root, client=ScriptedLearningClient())
        self.assertEqual(self._failure_trace(self.root)[0]["run_id"], trace["run_id"])

    def test_trace_write_failure_preserves_original_model_error(self):
        class FailingRoute(ScriptedLearningClient):
            def chat(self, messages, *, temperature, max_tokens):
                raise LLMRequestError("original model failure", status_code=403, retryable=False)

        assistant = LearningAssistant(self.root, client=FailingRoute())
        with patch.object(LearningOrchestrator, "_record_failed_run", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(LLMRequestError, "original model failure"):
                assistant.ask("什么是哈希冲突？")
        self.assertFalse((self.root / "local_state" / "failures").exists())

    def test_transient_routing_error_retries_once_within_budget(self):
        class FailOnce(ScriptedLearningClient):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def chat(self, messages, *, temperature, max_tokens):
                self.attempts += 1
                if self.attempts == 1:
                    raise LLMRequestError("Model API HTTP 503", status_code=503, retryable=True)
                return super().chat(messages, temperature=temperature, max_tokens=max_tokens)

        backend = FailOnce()
        usage_db = self.root / "local_state" / "qwen_usage.sqlite3"
        answer = LearningAssistant(self.root, client=BudgetedQwenClient(backend, usage_db)).ask(
            "什么是哈希冲突？", thread_id="transient-routing"
        )
        self.assertEqual(answer["learning"]["decision"], "answered")
        self.assertEqual(backend.attempts, 4)  # Failed route + successful route/reviewer/worker.
        self.assertEqual(BudgetedQwenClient.calls_used_at(usage_db), 4)
        self.assertTrue(any(event["kind"] == "routing_retry" for event in answer["events"]))

    def test_worker_quota_error_does_not_retry_or_save_session(self):
        class FailWorker(ScriptedLearningClient):
            def __init__(self):
                super().__init__()
                self.worker_attempts = 0

            def chat(self, messages, *, temperature, max_tokens):
                prompt = "\n".join(message.content for message in messages)
                if not any(marker in prompt for marker in
                           ("ROUTING_DECISION_JSON", "REVIEW_DECISION_JSON", "OUTPUT_REVIEW_JSON")):
                    self.worker_attempts += 1
                    raise LLMRequestError("Model API HTTP 403", status_code=403, retryable=False)
                return super().chat(messages, temperature=temperature, max_tokens=max_tokens)

        backend = FailWorker()
        usage_db = self.root / "local_state" / "qwen_usage.sqlite3"
        assistant = LearningAssistant(self.root, client=BudgetedQwenClient(backend, usage_db))
        with self.assertRaises(LLMRequestError):
            assistant.ask("什么是哈希冲突？", thread_id="worker-quota-failure")
        self.assertEqual(backend.worker_attempts, 1)
        self.assertEqual(BudgetedQwenClient.calls_used_at(usage_db), 3)
        self.assertFalse((self.root / "sessions" / "worker-quota-failure" / "snapshot.json").exists())

    def test_single_question_cli_reports_model_failure_without_traceback(self):
        class FailingAssistant:
            def __init__(self, workspace):
                pass

            def ask(self, question, *, thread_id):
                raise LLMRequestError(
                    "Model API HTTP 403 (AllocationQuota.FreeTierOnly)",
                    status_code=403, retryable=False,
                )

        stderr = io.StringIO()
        with patch("reasoning_agent_template.learning.LearningAssistant", FailingAssistant), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                main(["什么是哈希冲突？"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("模型请求失败", stderr.getvalue())
        self.assertIn("HTTP 403", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

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
