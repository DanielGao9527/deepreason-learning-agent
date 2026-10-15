"""One-command, offline acceptance check of the learning MVP's outcome paths."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path.insert(0, str(WORKBENCH / "src"))
sys.path.insert(0, str(WORKBENCH))

from reasoning_agent_template.learning import LearningAssistant, LearningRouteReviewError  # noqa: E402
from reasoning_agent_template.knowledge import LocalKnowledgeBase  # noqa: E402
from reasoning_agent_template.workflow import TemplateCoordinator, WorkflowContractError  # noqa: E402
from tests.test_learning_mvp import CompleteLearningReviewClient, ScriptedLearningClient  # noqa: E402
from tests.test_learning_route_review import RouteReviewClient  # noqa: E402


CASES = (
    ("guided_answer", "什么是哈希冲突？", "answered", "guided", "allow", "released_gate_only",
     ["route", "reviewer", "worker"], "supported"),
    ("deep_answer", "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。",
     "answered", "deep", "allow", "released_model_reviewed",
     ["route", "reviewer", "worker", "output_reviewer"], "supported"),
    ("deep_missing_coverage", "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。",
     "review_withheld", "deep", "allow", "withheld",
     ["route", "reviewer", "worker", "output_reviewer"], "supported"),
    ("no_evidence", "请解释 ZxqvPrime-99 的内部缓存协议。",
     "abstained_no_evidence", "guided", "allow", "released_gate_only",
     ["route", "reviewer"], "supported"),
    ("incomplete_comparison", "满二叉树和完全二叉树的定义有什么区别？",
     "abstained_incomplete_evidence", "guided", "allow", "released_gate_only",
     ["route", "reviewer"], "supported"),
    ("protected_action", "请删除生产环境数据。", "blocked", "deep", "deny", "withheld",
     ["route", "reviewer"], "supported"),
    ("review_withheld", "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。",
     "review_withheld", "deep", "allow", "withheld",
     ["route", "reviewer", "worker", "output_reviewer"], "issue"),
)


def _workspace(parent: Path, case_id: str) -> Path:
    workspace = parent / case_id
    shutil.copytree(WORKBENCH / "learning_mvp" / "knowledge", workspace / "knowledge")
    return workspace


def _check_equal(case_id: str, label: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise AssertionError(f"{case_id}: {label}: expected {expected!r}, got {observed!r}")


def _ordinary_case(parent: Path, spec: tuple) -> dict:
    case_id, question, decision, path, gate, release, calls, final_review = spec
    workspace = _workspace(parent, case_id)
    client = (CompleteLearningReviewClient() if case_id == "deep_answer"
              else ScriptedLearningClient(final_review=final_review))
    assistant = LearningAssistant(workspace, client=client)
    payload = assistant.ask(question, thread_id=case_id)
    observed_gate = payload["gates"]["decisions"][-1]["status"]
    _check_equal(case_id, "decision", payload["learning"]["decision"], decision)
    _check_equal(case_id, "path", payload["learning"]["path"], path)
    _check_equal(case_id, "gate", observed_gate, gate)
    _check_equal(case_id, "release", payload["output_release"]["status"], release)
    if case_id == "deep_missing_coverage":
        _check_equal(case_id, "coverage rejection", payload["output_release"]["reason"],
                     "answer_coverage_contract_failed")
    _check_equal(case_id, "model calls", client.calls, calls)
    saved = assistant.orchestrator.session_store.load(case_id)
    _check_equal(case_id, "published answer in session", saved.messages[-1]["content"], payload["answer"])
    if release == "withheld" and "结论取决于问题条件" in json.dumps(saved.to_dict(), ensure_ascii=False):
        raise AssertionError(f"{case_id}: withheld Worker draft reached the saved session")
    if decision.startswith("abstained") and "worker" in client.calls:
        raise AssertionError(f"{case_id}: Worker ran despite insufficient evidence")
    _check_equal(case_id, "failure trace count", len(list((workspace / "local_state" / "failures").glob("*.json"))), 0)
    plan_status = payload["workflow"].get("execution_plan", {}).get("status")
    if case_id == "incomplete_comparison":
        _check_equal(case_id, "evidence plan", plan_status, "blocked_missing_subject")
        _check_equal(case_id, "plan subtask events",
                     len([event for event in payload["events"] if event.get("kind") == "plan_task_completed"]), 3)
    return {
        "case": case_id,
        "expected_result": decision,
        "observed_result": payload["learning"]["decision"],
        "path": path,
        "gate": observed_gate,
        "release": payload["output_release"]["status"],
        "model_calls": client.calls,
        "qualified_evidence_count": len(payload["evidence"]["qualified_evidence_ids"]),
        "stage_trace": payload["state_machine"]["trace"],
        "session_saved": True,
        "plan_status": plan_status,
        "passed": True,
    }


def _invalid_handoff(parent: Path) -> dict:
    case_id = "invalid_handoff"
    workspace = _workspace(parent, case_id)
    client = ScriptedLearningClient()
    assistant = LearningAssistant(workspace, client=client)
    original_retrieve = TemplateCoordinator._retrieve

    def faulty_retrieve(coordinator, state):
        original_retrieve(coordinator, state)
        if not state.retrieval_results:
            raise AssertionError("Fault injection requires at least one retrieved candidate")
        first = state.retrieval_results[0]
        state.retrieval_results[0] = replace(first, evidence_id="ev_missing")

    with patch.object(TemplateCoordinator, "_retrieve", faulty_retrieve):
        try:
            assistant.ask("什么是哈希冲突？", thread_id=case_id)
        except WorkflowContractError as exc:
            _check_equal(case_id, "contract error", exc.code, "evidence_missing")
        else:
            raise AssertionError(f"{case_id}: invalid evidence was accepted")
    _check_equal(case_id, "model calls", client.calls, ["route", "reviewer"])
    saved = (workspace / "sessions" / case_id / "snapshot.json").exists()
    _check_equal(case_id, "session saved", saved, False)
    failure_files = list((workspace / "local_state" / "failures").glob("*.json"))
    _check_equal(case_id, "failure trace count", len(failure_files), 1)
    failure_trace = json.loads(failure_files[0].read_text(encoding="utf-8"))
    _check_equal(case_id, "terminal status", failure_trace["terminal_status"], "handoff_rejected")
    _check_equal(case_id, "reason code", failure_trace["reason_code"], "evidence_missing")
    _check_equal(case_id, "trace session status", failure_trace["session_saved"], False)
    return {
        "case": case_id,
        "expected_result": "WorkflowContractError:evidence_missing",
        "observed_result": "WorkflowContractError:evidence_missing",
        "path": "interrupted_before_worker",
        "gate": "not_reached",
        "release": "not_reached",
        "model_calls": client.calls,
        "qualified_evidence_count": None,
        "stage_trace": None,
        "session_saved": saved,
        "failure_trace": failure_trace["terminal_status"],
        "passed": True,
    }


def _invalid_route_review(parent: Path) -> dict:
    case_id = "invalid_route_review"
    workspace = _workspace(parent, case_id)
    client = RouteReviewClient("{}")
    try:
        LearningAssistant(workspace, client=client).ask("什么是哈希冲突？", thread_id=case_id)
    except LearningRouteReviewError as error:
        _check_equal(case_id, "reason", error.code, "invalid_review_status")
    else:
        raise AssertionError("invalid route review was allowed to continue")
    _check_equal(case_id, "model calls", client.calls, ["route", "reviewer"])
    saved = (workspace / "sessions" / case_id / "snapshot.json").exists()
    _check_equal(case_id, "session saved", saved, False)
    failures = list((workspace / "local_state" / "failures").glob("*.json"))
    _check_equal(case_id, "failure trace count", len(failures), 1)
    trace = json.loads(failures[0].read_text(encoding="utf-8"))
    _check_equal(case_id, "terminal", trace["terminal_status"], "route_review_failed")
    _check_equal(case_id, "reason", trace["reason_code"], "invalid_review_status")
    return {
        "case": case_id, "expected_result": "route_review_failed",
        "observed_result": "route_review_failed", "path": "interrupted_before_workflow",
        "gate": "not_reached", "release": "not_reached", "model_calls": client.calls,
        "qualified_evidence_count": None, "stage_trace": None, "session_saved": saved,
        "failure_trace": trace["terminal_status"], "passed": True,
    }


def _top_k_recovery(parent: Path) -> dict:
    case_id = "top_k_recovery"
    workspace = parent / case_id
    corpus = workspace / "knowledge"
    corpus.mkdir(parents=True)
    left, right = "满二叉树", "完全二叉树"
    (corpus / "left_definition.md").write_text(
        f"{left}：每个内部结点恰有两个孩子。 "
        + " ".join(f"filler{i}" for i in range(100)), encoding="utf-8",
    )
    (corpus / "right_definition.md").write_text(
        f"{right}：除末层外均填满，末层从左向右填充。", encoding="utf-8",
    )
    for index in range(5):
        (corpus / f"distractor_{index}.md").write_text(f"满 二叉树 {index}", encoding="utf-8")
    attempts = []
    original_retrieve = LocalKnowledgeBase.retrieve

    def tracked_retrieve(kb, query, **kwargs):
        results = original_retrieve(kb, query, **kwargs)
        attempts.append({"query": query, "top_k": kwargs["top_k"],
                         "min_score": kwargs["min_score"],
                         "subject_matches": sum(query in item.text for item in results)})
        return results

    client = ScriptedLearningClient()
    with patch.object(LocalKnowledgeBase, "retrieve", tracked_retrieve):
        payload = LearningAssistant(workspace, client=client).ask(
            "满二叉树和完全二叉树的定义有什么区别？", thread_id=case_id,
        )
    plan = payload["workflow"]["execution_plan"]
    _check_equal(case_id, "decision", payload["learning"]["decision"], "answered")
    _check_equal(case_id, "plan status", plan["status"], "completed")
    _check_equal(case_id, "top-k attempts", [item["top_k"] for item in attempts], [4, 12, 4])
    _check_equal(case_id, "subject matches", [item["subject_matches"] for item in attempts], [0, 1, 1])
    _check_equal(case_id, "score floors", [item["min_score"] for item in attempts], [0.08] * 3)
    _check_equal(case_id, "model calls", client.calls, ["route", "reviewer", "worker"])
    _check_equal(case_id, "failure files", len(list((workspace / "local_state" / "failures").glob("*.json"))), 0)
    return {
        "case": case_id,
        "expected_result": "answered_after_one_wider_read",
        "observed_result": "answered_after_one_wider_read",
        "path": "bounded_retrieval_recovery",
        "gate": payload["gates"]["decisions"][-1]["status"],
        "release": payload["output_release"]["status"],
        "model_calls": client.calls,
        "qualified_evidence_count": len(payload["evidence"]["qualified_evidence_ids"]),
        "stage_trace": payload["state_machine"]["trace"],
        "session_saved": (workspace / "sessions" / case_id / "snapshot.json").exists(),
        "retrieval_attempts": attempts,
        "passed": True,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="deepreason-mvp-acceptance-") as temp:
        parent = Path(temp)
        rows = [_ordinary_case(parent, spec) for spec in CASES]
        rows.append(_invalid_handoff(parent))
        rows.append(_top_k_recovery(parent))
        rows.append(_invalid_route_review(parent))
    spec = json.loads((WORKBENCH / "learning_mvp" / "configs" / "workflows" /
                       "learning.workflow.json").read_text(encoding="utf-8"))
    declared = {(edge["from"], edge["to"]): edge["id"] for edge in spec["edges"]}
    traversed = {
        (start, end)
        for row in rows if row["stage_trace"]
        for start, end in zip(row["stage_trace"], row["stage_trace"][1:])
    }
    report = {
        "kind": "offline_scripted_mvp_acceptance",
        "scope": "Selected answer, refusal, handoff/review failure and bounded retrieval cases; not exhaustive control-flow coverage",
        "passed": sum(row["passed"] for row in rows),
        "total": len(rows),
        "real_qwen_calls": 0,
        "workflow_edges": {
            "declared": len(declared),
            "observed_from_adjacent_nodes": len(traversed & declared.keys()),
            "unobserved_ids": [edge_id for endpoints, edge_id in declared.items() if endpoints not in traversed],
            "unique_complete_traces": len({tuple(row["stage_trace"]) for row in rows if row["stage_trace"]}),
        },
        "cases": rows,
    }
    destination = ROOT / "artifacts" / "validation" / "learning_mvp_paths.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(destination),
        "passed": report["passed"],
        "total": report["total"],
        "real_qwen_calls": 0,
        "workflow_edges": report["workflow_edges"],
        "cases": [{key: row[key] for key in ("case", "observed_result", "gate", "release", "model_calls", "passed")}
                  for row in rows],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
