"""Validate accounting failure boundaries and bind manual scores to frozen content."""
from copy import deepcopy
from contextlib import closing, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from reasoning_agent_template.learning_experiment import (
    ExperimentClient, METRICS, call_summary, make_review_packet, score_manual_review,
    terminal_model_failures,
)
from reasoning_agent_template.llm import ChatMessage, ChatResult, LLMRequestError
from reasoning_agent_template.learning import BudgetedQwenClient
from tests.test_learning_mvp import ScriptedLearningClient


class CountingBackend:
    model = "fixture-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, messages, *, temperature, max_tokens):
        value = self.responses[self.calls]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return ChatResult(content="fixture answer", model=self.model, raw=value)


def ask(client):
    return client.chat([ChatMessage("system", "worker"), ChatMessage("user", "private input")],
                       temperature=0.2, max_tokens=100)


def experiment_fixture():
    return {"experiment_id": "fixture-exp", "status": "completed", "source": "offline-script", "cases": [{
        "id": "comparison", "question": "fixture comparison", "rubric": {"premises": "explain condition"},
        "baseline": {"answer": "omitted premise", "decision": "answered", "qualified_evidence": [{"text": "source"}]},
        "approved": {"answer": "explicit premise", "decision": "answered", "qualified_evidence": [{"text": "source"}]},
    }]}


class ExperimentAccountingTests(unittest.TestCase):
    def test_role_tags_follow_runtime_protocol_prefixes_and_ignore_user_marker_mentions(self):
        client = ExperimentClient(CountingBackend([{}, {}, {}, {}]), max_calls=4)
        for system, request in (
            ("coordinator", "ROUTING_DECISION_JSON schema:\n{}"),
            ("reviewer", "REVIEW_DECISION_JSON schema:\n{}"),
            ("You are an independent final-answer reviewer. OUTPUT_REVIEW_JSON", "{}"),
            ("worker", "证据策略：用户问 OUTPUT_REVIEW_JSON 是什么"),
        ):
            client.chat([ChatMessage("system", system), ChatMessage("user", request)], temperature=0, max_tokens=10)
        self.assertEqual([call["role"] for call in client.calls], ["route", "reviewer", "output_reviewer", "worker"])

    def test_known_usage_is_whitelisted_and_missing_usage_stays_unknown(self):
        backend = CountingBackend([{"usage": {"prompt_tokens": 12, "completion_tokens": 5, "secret": "RAW-SECRET"}}, {}])
        client = ExperimentClient(backend, max_calls=3)
        ask(client)
        summary = call_summary(client.calls)
        self.assertEqual((summary["prompt_tokens"], summary["completion_tokens"]), (12, 5))
        ask(client)
        summary = call_summary(client.calls)
        self.assertFalse(summary["usage_complete"])
        self.assertIsNone(summary["prompt_tokens"])
        self.assertEqual(summary["known_prompt_tokens"], 12)
        self.assertNotIn("RAW-SECRET", json.dumps(client.calls))
        self.assertNotIn("private input", json.dumps(client.calls))

    def test_failed_retry_counts_and_cannot_hide_unknown_billed_tokens(self):
        backend = CountingBackend([LLMRequestError("sensitive body", status_code=503),
                                   {"usage": {"prompt_tokens": 8, "completion_tokens": 3}}])
        client = ExperimentClient(backend, max_calls=3)
        with self.assertRaises(LLMRequestError):
            ask(client)
        ask(client)
        summary = call_summary(client.calls)
        self.assertEqual((summary["forwarded_attempts"], summary["failed_attempts"]), (2, 1))
        self.assertIsNone(summary["completion_tokens"])
        self.assertEqual(summary["known_completion_tokens"], 3)
        self.assertNotIn("sensitive body", json.dumps(client.calls))

    def test_non_retryable_failure_latches_before_later_role_can_send(self):
        backend = CountingBackend([LLMRequestError("KEY-MUST-NOT-LEAK", retryable=False, status_code=403), {}])
        client = ExperimentClient(backend, max_calls=3)
        with self.assertRaises(LLMRequestError):
            ask(client)
        with self.assertRaises(LLMRequestError) as caught:
            ask(client)
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(client.rejected_calls, 1)
        self.assertNotIn("KEY-MUST-NOT-LEAK", json.dumps(client.calls))

    def test_cap_prevents_third_send_and_model_change_is_rejected(self):
        backend = CountingBackend([{}, {}, {}])
        client = ExperimentClient(backend, max_calls=2)
        ask(client)
        ask(client)
        with self.assertRaises(LLMRequestError):
            ask(client)
        self.assertEqual(backend.calls, 2)
        fresh = ExperimentClient(backend, max_calls=3)
        backend.model = "different-model"
        with self.assertRaises(LLMRequestError):
            ask(fresh)
        self.assertEqual(backend.calls, 2)
        self.assertEqual(fresh.blocked_reason, "requested_model_changed")

    def test_boolean_or_negative_usage_is_not_valid_accounting(self):
        for usage in ({"prompt_tokens": True, "completion_tokens": 2},
                      {"prompt_tokens": 4, "completion_tokens": -1}):
            with self.subTest(usage=usage):
                client = ExperimentClient(CountingBackend([{"usage": usage}]), max_calls=1)
                ask(client)
                self.assertIsNone(call_summary(client.calls)["prompt_tokens"])

    def test_review_service_failure_is_not_scored_as_an_answer_rejection(self):
        failed = [{"role": "output_reviewer", "status": "failed"}]
        self.assertEqual(terminal_model_failures(failed), ["output_reviewer"])
        self.assertEqual(terminal_model_failures([*failed, {"role": "output_reviewer", "status": "succeeded"}]), [])

    def test_returned_model_change_stops_comparison_even_when_requested_alias_is_unchanged(self):
        class ChangingModel(CountingBackend):
            def chat(self, messages, *, temperature, max_tokens):
                result = super().chat(messages, temperature=temperature, max_tokens=max_tokens)
                return ChatResult(result.content, "revision-1" if self.calls == 1 else "revision-2", result.raw)
        backend = ChangingModel([{}, {}, {}])
        client = ExperimentClient(backend, max_calls=3)
        ask(client)
        with self.assertRaises(LLMRequestError):
            ask(client)
        with self.assertRaises(LLMRequestError):
            ask(client)
        self.assertEqual(backend.calls, 2)
        self.assertEqual(client.blocked_reason, "returned_model_changed_or_unknown")


class ManualReviewBindingTests(unittest.TestCase):
    def setUp(self):
        self.experiment = experiment_fixture()
        self.packet, self.review = make_review_packet(self.experiment)

    def test_pending_review_has_no_quality_rate_and_no_variant_names(self):
        score = score_manual_review(self.experiment, self.packet, self.review)
        self.assertEqual(score["annotated_samples"], 0)
        self.assertFalse(score["real_model_quality_measured"])
        self.assertIsNone(score["metrics"]["premises"]["pass_count_delta"])
        self.assertNotIn("baseline", json.dumps(self.packet))
        self.assertNotIn("approved", json.dumps(self.packet))

    def test_complete_scores_compare_variants_without_assuming_a_is_baseline(self):
        self.review.update(reviewer="fixture-reviewer", method="human")
        samples = {sample["sample_id"]: sample for sample in self.packet["samples"]}
        for entry in self.review["entries"]:
            label = "pass" if samples[entry["sample_id"]]["answer"] == "explicit premise" else "fail"
            entry["labels"] = {metric: label for metric in METRICS}
            entry["rationale"] = "synthetic calibration only"
        score = score_manual_review(self.experiment, self.packet, self.review)
        self.assertEqual(score["metrics"]["premises"]["pass_count_delta"], 1)
        self.assertTrue(score["human_review_complete"])
        self.assertFalse(score["real_model_quality_measured"])  # Script fixtures cannot become real-model metrics.

    def test_changed_answer_or_evidence_cannot_reuse_old_scores(self):
        for field, value in (("answer", "changed answer"), ("qualified_evidence", [{"text": "changed source"}])):
            altered = deepcopy(self.experiment)
            altered["cases"][0]["baseline"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "changed"):
                score_manual_review(altered, self.packet, self.review)

    def test_duplicate_sample_wrong_answer_hash_or_incomplete_entries_are_rejected(self):
        for fault in ("duplicate", "wrong_hash", "missing"):
            review = deepcopy(self.review)
            if fault == "duplicate":
                review["entries"][1] = deepcopy(review["entries"][0])
            elif fault == "wrong_hash":
                review["entries"][0]["answer_sha256"] = "wrong"
            else:
                review["entries"].pop()
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                score_manual_review(self.experiment, self.packet, review)

    def test_failed_label_requires_rationale_and_declared_reviewer(self):
        self.review["entries"][0]["labels"]["premises"] = "fail"
        with self.assertRaisesRegex(ValueError, "rationale"):
            score_manual_review(self.experiment, self.packet, self.review)
        self.review["entries"][0]["rationale"] = "omitted the required condition"
        with self.assertRaisesRegex(ValueError, "reviewer"):
            score_manual_review(self.experiment, self.packet, self.review)

    def test_aborted_experiment_is_not_a_quality_comparison(self):
        self.experiment["status"] = "aborted"
        with self.assertRaisesRegex(ValueError, "incomplete_experiment"):
            make_review_packet(self.experiment)


class ExperimentCliWiringTests(unittest.TestCase):
    """Exercise the explicit Qwen branch with a fake backend and isolated counter."""

    def setUp(self):
        script = Path(__file__).resolve().parents[3] / "scripts" / "run_learning_experiment.py"
        spec = importlib.util.spec_from_file_location("learning_experiment_cli_test", script)
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = self.root / "usage.sqlite3"

    def test_qwen_branch_reuses_shared_persistent_counter_without_a_real_provider(self):
        budget = BudgetedQwenClient(ScriptedLearningClient(), self.db)
        with patch.object(self.cli, "ROOT", self.root), patch.object(self.cli, "USAGE_DB", self.db), \
             patch.object(self.cli, "qwen_client_from_env", return_value=budget), redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.main(["--qwen", "--max-calls", "32"]), 0)
        self.assertEqual(BudgetedQwenClient.calls_used_at(self.db), 16)
        folder = next((self.root / "artifacts" / "experiments").iterdir())
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["repository_reservations_after"], 16)
        self.assertEqual(manifest["status"], "completed")
        self.assertTrue((folder / "review.json").is_file())

    def test_quota_failure_stops_the_batch_after_one_reserved_attempt(self):
        backend = CountingBackend([LLMRequestError("provider-secret", retryable=False, status_code=403)])
        with patch.object(self.cli, "ROOT", self.root), patch.object(self.cli, "USAGE_DB", self.db), \
             patch.object(self.cli, "qwen_client_from_env", return_value=BudgetedQwenClient(backend, self.db)), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.main(["--qwen"]), 2)
        self.assertEqual(BudgetedQwenClient.calls_used_at(self.db), 1)
        self.assertEqual(backend.calls, 1)
        folder = next((self.root / "artifacts" / "experiments").iterdir())
        raw = (folder / "manifest.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw)["status"], "aborted")
        self.assertNotIn("provider-secret", raw)
        self.assertFalse((folder / "review_packet.json").exists())

    def test_default_plan_and_insufficient_allowance_do_not_initialize_provider(self):
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute("CREATE TABLE usage(id INTEGER PRIMARY KEY, count INTEGER)")
                connection.execute("INSERT INTO usage VALUES(1,98)")
        with patch.object(self.cli, "USAGE_DB", self.db), \
             patch.object(self.cli, "qwen_client_from_env") as factory, redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.main([]), 0)
            with self.assertRaisesRegex(ValueError, "not_enough_repository"):
                self.cli.main(["--qwen", "--max-calls", "4"])
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
