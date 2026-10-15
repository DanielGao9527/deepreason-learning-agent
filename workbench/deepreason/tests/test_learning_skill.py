import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reasoning_agent_template.learning import LearningAssistant, LearningOrchestrator, learning_config, main as learning_main
from reasoning_agent_template.learning_notes import LearningNoteStore
from reasoning_agent_template.learning_skill import LearningSkillError, LearningSkillStore
from reasoning_agent_template.models import AgentState, GateDecision
from tests.test_learning_mvp import CORPUS, ReviewedLearningClient


class LearningSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.notes = LearningNoteStore(self.root)
        self.skills = LearningSkillStore(self.root)
        self.notes.save(thread_id="learner", operation_id="feedback-1",
                        body="比较题的回答应先说成立条件，否则我容易混淆。", expected_version=0)

    def tearDown(self):
        self.temp.cleanup()

    def test_candidate_is_sourced_and_three_cases_compare_old_and_new_without_activating(self):
        candidate = self.skills.propose_from_note(
            thread_id="learner", operation_id="feedback-1", feedback_kind="missing_preconditions",
        )
        self.assertEqual(candidate["evaluation"]["passed"], 3)
        self.assertEqual(candidate["evaluation"]["total"], 3)
        self.assertEqual([(case["before"], case["candidate"]) for case in candidate["evaluation"]["cases"]],
                         [(False, True), (False, False), (False, False)])
        self.assertEqual(candidate["source_note_id"], self.notes.receipt("learner", "feedback-1")["note_id"])
        self.assertEqual(self.skills.active()["version"], 0)
        self.assertEqual(self.skills.instruction_for("满二叉树和完全二叉树有什么区别？", evidence_ready=True), "")

    def test_missing_note_and_wrong_thread_cannot_create_candidate(self):
        for thread, operation in (("other", "feedback-1"), ("learner", "missing")):
            with self.subTest(thread=thread, operation=operation), self.assertRaisesRegex(
                LearningSkillError, "source_note_not_found",
            ):
                self.skills.propose_from_note(thread_id=thread, operation_id=operation,
                                              feedback_kind="missing_preconditions")
        self.assertFalse(self.skills.path.exists())

    def test_unrelated_note_is_not_treated_as_feedback(self):
        self.notes.save(thread_id="learner", operation_id="ordinary-note",
                        body="复习哈希冲突的定义", expected_version=1)
        with self.assertRaisesRegex(LearningSkillError, "source_note_not_comparison_feedback"):
            self.skills.propose_from_note(thread_id="learner", operation_id="ordinary-note",
                                          feedback_kind="missing_preconditions")
        self.assertFalse(self.skills.path.exists())

    def test_overbroad_trigger_fails_negative_case_and_cannot_be_approved(self):
        candidate = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                   feedback_kind="missing_preconditions", trigger="any")
        self.assertEqual(candidate["evaluation"]["passed"], 2)
        self.assertEqual(candidate["evaluation"]["cases"][-1]["candidate"], True)
        with self.assertRaisesRegex(LearningSkillError, "candidate_evaluation_failed"):
            self.skills.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                                approved_by="explicit-local-command")
        self.assertEqual(self.skills.active()["version"], 0)

    def test_edited_candidate_or_evaluation_cannot_bypass_hash_bound_approval(self):
        candidate = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                   feedback_kind="missing_preconditions")
        with closing(sqlite3.connect(self.skills.path)) as db:
            db.execute("UPDATE candidates SET instruction='edited' WHERE candidate_id=?",
                       (candidate["candidate_id"],))
            db.commit()
        with self.assertRaisesRegex(LearningSkillError, "candidate_content_changed"):
            self.skills.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                                approved_by="local")
        second = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                feedback_kind="missing_preconditions")
        with closing(sqlite3.connect(self.skills.path)) as db:
            db.execute("UPDATE candidates SET evaluation='{}' WHERE candidate_id=?",
                       (second["candidate_id"],))
            db.commit()
        with self.assertRaisesRegex(LearningSkillError, "candidate_evaluation_changed"):
            self.skills.approve(second["candidate_id"], expected_hash=second["content_hash"],
                                approved_by="local")
        self.assertEqual(self.skills.active()["version"], 0)

    def test_edited_active_instruction_is_not_injected(self):
        candidate = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                   feedback_kind="missing_preconditions")
        self.skills.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                            approved_by="local")
        with closing(sqlite3.connect(self.skills.path)) as db:
            db.execute("UPDATE versions SET instruction='tampered' WHERE version=1")
            db.commit()
        with self.assertRaisesRegex(LearningSkillError, "active_content_hash_mismatch"):
            self.skills.instruction_for("满二叉树和完全二叉树有什么区别？", evidence_ready=True)

    def test_rollback_rejects_tampered_target_version(self):
        candidate = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                   feedback_kind="missing_preconditions")
        self.skills.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                            approved_by="local")
        with closing(sqlite3.connect(self.skills.path)) as db:
            db.execute("UPDATE versions SET instruction='tampered' WHERE version=0")
            db.commit()
        with self.assertRaisesRegex(LearningSkillError, "target_content_hash_mismatch"):
            self.skills.rollback(0, expected_current_hash=candidate["content_hash"], approved_by="local")
        self.assertEqual(self.skills.active()["version"], 1)

    def test_approval_is_bound_to_candidate_hash_and_base_version_then_rollback(self):
        first = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                              feedback_kind="missing_preconditions")
        stale = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                              feedback_kind="missing_preconditions")
        with self.assertRaisesRegex(LearningSkillError, "explicit_approval_required"):
            self.skills.approve(first["candidate_id"], expected_hash=first["content_hash"], approved_by=None)
        with self.assertRaisesRegex(LearningSkillError, "candidate_hash_mismatch"):
            self.skills.approve(first["candidate_id"], expected_hash="wrong", approved_by="local")
        applied = self.skills.approve(first["candidate_id"], expected_hash=first["content_hash"],
                                      approved_by="explicit-local-command")
        self.assertEqual(applied["version"], 1)
        self.assertEqual(applied["gate_decision"]["status"], "allow")
        self.assertEqual(applied["gate_decision"]["required_evidence"], [first["source_note_id"]])
        self.assertEqual(LearningSkillStore(self.root).active()["content_hash"], first["content_hash"])
        with self.assertRaisesRegex(LearningSkillError, "base_version_changed"):
            self.skills.approve(stale["candidate_id"], expected_hash=stale["content_hash"], approved_by="local")
        with self.assertRaisesRegex(LearningSkillError, "active_hash_mismatch"):
            self.skills.rollback(0, expected_current_hash="wrong", approved_by="local")
        rolled_back = self.skills.rollback(0, expected_current_hash=first["content_hash"],
                                           approved_by="explicit-local-command")
        self.assertEqual(rolled_back["version"], 0)
        self.assertEqual(rolled_back["gate_decision"]["status"], "allow")
        self.assertEqual(LearningSkillStore(self.root).active()["version"], 0)

    def test_only_approved_comparison_with_evidence_changes_worker_system_prompt(self):
        candidate = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                   feedback_kind="missing_preconditions")
        self.skills.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                            approved_by="explicit-local-command")
        orchestrator = LearningOrchestrator(config=learning_config(self.root), workspace_root=self.root)
        state = AgentState()
        state.gate_decisions = [GateDecision(gate_id="g", risk_level="medium", status="allow", reasons=[])]
        state.qualified_evidence_ids = ["e1", "e2"]
        state.execution_plan = {"status": "completed"}

        def prompt(question):
            return orchestrator._deepseek_messages(question, state, short_term_memory=[],
                                                    long_term_memory=[])[0].content

        comparison = "满二叉树和完全二叉树有什么区别？"
        self.assertIn("已审批教学 Skill", prompt(comparison))
        self.assertNotIn("已审批教学 Skill", prompt("二叉树是什么？"))
        state.execution_plan = {"status": "incomplete"}
        self.assertNotIn("已审批教学 Skill", prompt(comparison))
        state.execution_plan = {"status": "completed"}
        state.gate_decisions[-1] = GateDecision(gate_id="g", risk_level="medium", status="deny", reasons=[])
        self.assertNotIn("已审批教学 Skill", prompt(comparison))

    def test_full_comparison_run_loads_approved_skill_and_rollback_removes_it(self):
        shutil.copytree(CORPUS, self.root / "knowledge")
        (self.root / "knowledge" / "shape_definitions.md").write_text(
            "满二叉树：每个内部结点恰有两个非空孩子。"
            "完全二叉树：除末层外各层填满，末层从左向右填充。", encoding="utf-8",
        )
        question = "满二叉树和完全二叉树的定义有什么区别？"

        class CapturingClient(ReviewedLearningClient):
            def __init__(self):
                super().__init__()
                self.worker_system = ""

            def chat(self, messages, *, temperature, max_tokens):
                combined = "\n".join(message.content for message in messages)
                if all(marker not in combined for marker in
                       ("ROUTING_DECISION_JSON", "REVIEW_DECISION_JSON", "OUTPUT_REVIEW_JSON")):
                    self.worker_system = messages[0].content
                return super().chat(messages, temperature=temperature, max_tokens=max_tokens)

        def run(thread):
            client = CapturingClient()
            answer = LearningAssistant(self.root, client=client).ask(question, thread_id=thread)
            self.assertEqual(answer["learning"]["decision"], "answered")
            self.assertIn("worker", client.calls)
            return client.worker_system

        self.assertNotIn("已审批教学 Skill", run("before"))
        candidate = self.skills.propose_from_note(thread_id="learner", operation_id="feedback-1",
                                                   feedback_kind="missing_preconditions")
        applied = self.skills.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                                      approved_by="local")
        self.assertIn("已审批教学 Skill", run("after"))
        self.skills.rollback(0, expected_current_hash=applied["content_hash"], approved_by="local")
        self.assertNotIn("已审批教学 Skill", run("rolled-back"))

    def test_cli_lifecycle_needs_no_qwen_and_hashes_are_checked(self):
        common = ["--workspace", str(self.root), "--thread", "learner"]

        def command(*args):
            output = io.StringIO()
            with redirect_stdout(output), patch("reasoning_agent_template.learning.qwen_client_from_env",
                                                side_effect=AssertionError("must not call Qwen")):
                exit_code = learning_main([*common, *args])
            return exit_code, output.getvalue()

        code, raw = command("--skill-propose-from-note", "feedback-1")
        self.assertEqual(code, 0)
        candidate = json.loads(raw)
        self.assertEqual(candidate["evaluation"]["passed"], 3)
        self.assertEqual(command("--skill-approve", candidate["candidate_id"], "--candidate-hash", "wrong")[0], 2)
        code, raw = command("--skill-approve", candidate["candidate_id"],
                            "--candidate-hash", candidate["content_hash"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(raw)["version"], 1)
        self.assertEqual(json.loads(command("--skill-status")[1])["version"], 1)
        code, raw = command("--skill-rollback", "0", "--expected-current-hash", candidate["content_hash"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(raw)["version"], 0)


if __name__ == "__main__":
    unittest.main()
