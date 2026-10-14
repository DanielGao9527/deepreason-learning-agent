"""The answer probe diagnoses current releases without claiming semantic truth."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from reasoning_agent_template.answer_eval import score_case
from reasoning_agent_template.learning import LearningAssistant
from tests.test_learning_mvp import ScriptedLearningClient


ROOT = Path(__file__).resolve().parents[1]
RUBRIC = json.loads((ROOT / "evals" / "learning_answer_probe_v1.json").read_text(encoding="utf-8"))
CORPUS = ROOT / "learning_mvp" / "knowledge"


class AnswerProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        shutil.copytree(CORPUS, self.workspace / "knowledge")

    def tearDown(self):
        self.temp.cleanup()

    def test_released_generic_concept_answer_misses_required_facts_despite_evidence(self):
        case = RUBRIC["cases"][0]
        client = ScriptedLearningClient()
        result = LearningAssistant(self.workspace, client=client).ask(case["question"], thread_id="probe")
        scored = score_case(case, result, list(client.calls))
        self.assertEqual(scored["release"], "released_gate_only")
        self.assertTrue(scored["decision_match"])
        self.assertEqual(scored["qualified_anchor_hits"], [True])
        self.assertFalse(scored["proxy_pass"])
        self.assertEqual(scored["failure_layer"], "answer_wording")

    def test_literal_proxy_can_accept_factually_reversed_claim(self):
        case = RUBRIC["cases"][0]
        client = ScriptedLearningClient()
        result = LearningAssistant(self.workspace, client=client).ask(case["question"], thread_id="probe")
        altered = deepcopy(result)
        altered["answer"] = "两个不同的键绝不会映射到同一槽位，所以哈希冲突不存在。"
        scored = score_case(case, altered, list(client.calls))
        self.assertTrue(scored["proxy_pass"])
        # This is an intentional false positive: token coverage is not entailment.

    def test_missing_source_anchor_is_not_mislabeled_as_answer_wording_failure(self):
        case = RUBRIC["cases"][0]
        client = ScriptedLearningClient()
        result = LearningAssistant(self.workspace, client=client).ask(case["question"], thread_id="probe")
        changed = deepcopy(case)
        changed["source_anchors"][0]["contains"] = "not in the qualified source"
        scored = score_case(changed, result, list(client.calls))
        self.assertEqual(scored["failure_layer"], "qualified_evidence")


if __name__ == "__main__":
    unittest.main()
