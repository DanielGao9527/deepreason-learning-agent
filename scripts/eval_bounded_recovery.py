"""Fixed-initial-state, offline ablation of the two-subject top-k recovery budget."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path.insert(0, str(WORKBENCH / "src"))
sys.path.insert(0, str(WORKBENCH))

from reasoning_agent_template.knowledge import LocalKnowledgeBase  # noqa: E402
from reasoning_agent_template.learning import LearningAssistant, _corpus_fingerprint  # noqa: E402
from reasoning_agent_template.learning_plan import build_comparison_plan  # noqa: E402
from tests.test_learning_mvp import ReviewedLearningClient  # noqa: E402


QUESTION = "满二叉树和完全二叉树的定义有什么区别？"


def _make_corpus(root: Path, scenario: str) -> Path:
    corpus = root / "knowledge"
    corpus.mkdir(parents=True)
    if scenario == "both_visible":
        (corpus / "definitions.md").write_text(
            "满二叉树：每个内部结点恰有两个孩子。完全二叉树：末层从左向右填充。",
            encoding="utf-8",
        )
        return corpus
    if scenario == "top_k_omission":
        (corpus / "left_definition.md").write_text(
            "满二叉树：每个内部结点恰有两个孩子。 "
            + " ".join(f"filler{i}" for i in range(100)), encoding="utf-8",
        )
    (corpus / "right_definition.md").write_text(
        "完全二叉树：除末层外均填满，末层从左向右填充。", encoding="utf-8",
    )
    for index in range(5):
        (corpus / f"distractor_{index}.md").write_text(f"满 二叉树 {index}", encoding="utf-8")
    return corpus


def _trial(parent: Path, scenario: str, budget: int) -> dict:
    root = parent / f"{scenario}-{budget}"
    corpus = _make_corpus(root, scenario)
    calls = []
    original_retrieve = LocalKnowledgeBase.retrieve

    def tracked_retrieve(kb, query, **kwargs):
        results = original_retrieve(kb, query, **kwargs)
        calls.append({"subject": query, "top_k": kwargs["top_k"],
                      "min_score": kwargs["min_score"],
                      "matching_chunks": sum(query in item.text for item in results)})
        return results

    def budgeted_plan(left: str, right: str):
        plan = build_comparison_plan(left, right)
        plan["max_retrieval_attempts_per_subject"] = budget
        return plan

    client = ReviewedLearningClient()
    with patch.object(LocalKnowledgeBase, "retrieve", tracked_retrieve), patch(
        "reasoning_agent_template.learning.build_comparison_plan", side_effect=budgeted_plan,
    ):
        result = LearningAssistant(root, client=client).ask(QUESTION, thread_id="fresh")
    return {
        "scenario": scenario,
        "budget": budget,
        "corpus_fingerprint": _corpus_fingerprint(corpus),
        "decision": result["learning"]["decision"],
        "plan_status": result["workflow"]["execution_plan"]["status"],
        "qualified_evidence_count": len(result["evidence"]["qualified_evidence_ids"]),
        "retrieval_calls": calls,
        "model_calls": client.calls,
        "session_saved": (root / "sessions" / "fresh" / "snapshot.json").exists(),
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="deepreason-recovery-eval-") as temp:
        parent = Path(temp)
        rows = [_trial(parent, scenario, budget)
                for scenario in ("both_visible", "top_k_omission", "source_absent")
                for budget in (1, 2)]
    paired = {scenario: {row["budget"]: row for row in rows if row["scenario"] == scenario}
              for scenario in ("both_visible", "top_k_omission", "source_absent")}
    for scenario, pair in paired.items():
        if pair[1]["corpus_fingerprint"] != pair[2]["corpus_fingerprint"]:
            raise AssertionError(f"{scenario}: initial corpora differ")
    expected = {
        "both_visible": ("answered", "answered"),
        "top_k_omission": ("abstained_incomplete_evidence", "answered"),
        "source_absent": ("abstained_incomplete_evidence", "abstained_incomplete_evidence"),
    }
    for scenario, decisions in expected.items():
        observed = (paired[scenario][1]["decision"], paired[scenario][2]["decision"])
        if observed != decisions:
            raise AssertionError(f"{scenario}: expected {decisions}, got {observed}")
    report = {
        "kind": "offline_bounded_recovery_ablation",
        "scope": "Three scripted scenarios, one run per condition; no claim about real answer accuracy or latency",
        "real_qwen_calls": 0,
        "cases": rows,
    }
    destination = ROOT / "artifacts" / "analysis" / "bounded_recovery_ablation.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(destination), "real_qwen_calls": 0,
                      "comparisons": [
                          {"scenario": scenario,
                           "budget_1": pair[1]["decision"], "budget_2": pair[2]["decision"],
                           "retrieval_calls_1": len(pair[1]["retrieval_calls"]),
                           "retrieval_calls_2": len(pair[2]["retrieval_calls"]),
                           "model_calls_1": len(pair[1]["model_calls"]),
                           "model_calls_2": len(pair[2]["model_calls"])}
                          for scenario, pair in paired.items()],
                      }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
