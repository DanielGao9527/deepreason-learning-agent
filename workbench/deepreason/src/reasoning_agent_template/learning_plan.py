"""A bounded, executable evidence plan for explicit two-subject learning questions."""
from __future__ import annotations

from typing import Any


class LearningPlanError(ValueError):
    """Reject a malformed plan before any retrieval or model answer."""


def build_comparison_plan(left: str, right: str) -> dict[str, Any]:
    return {
        "kind": "two_subject_evidence",
        "max_steps": 3,
        "tasks": [
            {
                "id": "lookup_left", "depends_on": [], "handler": "local_rag",
                "query": left, "subject": left,
                "expected_artifact": "source_chunks",
                "completion_condition": "at_least_one_chunk_contains_subject",
            },
            {
                "id": "lookup_right", "depends_on": [], "handler": "local_rag",
                "query": right, "subject": right,
                "expected_artifact": "source_chunks",
                "completion_condition": "at_least_one_chunk_contains_subject",
            },
            {
                "id": "join_evidence", "depends_on": ["lookup_left", "lookup_right"],
                "handler": "join_evidence", "expected_artifact": "candidate_evidence_ids",
                "completion_condition": "both_subjects_have_candidates",
            },
        ],
    }


def ordered_plan_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate dependencies and return a bounded topological execution order."""
    if not isinstance(plan, dict) or plan.get("kind") != "two_subject_evidence":
        raise LearningPlanError("unsupported_plan")
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 3 or plan.get("max_steps") != 3:
        raise LearningPlanError("invalid_step_budget")
    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise LearningPlanError("invalid_task")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id or task_id in by_id:
            raise LearningPlanError("duplicate_or_missing_task_id")
        if task.get("handler") not in {"local_rag", "join_evidence"}:
            raise LearningPlanError("unavailable_handler")
        if not all(isinstance(task.get(key), str) and task[key].strip()
                   for key in ("expected_artifact", "completion_condition")):
            raise LearningPlanError("missing_completion_contract")
        if task["handler"] == "local_rag" and not all(
            isinstance(task.get(key), str) and task[key].strip() for key in ("query", "subject")
        ):
            raise LearningPlanError("missing_retrieval_query")
        by_id[task_id] = task
    if set(by_id) != {"lookup_left", "lookup_right", "join_evidence"}:
        raise LearningPlanError("invalid_comparison_tasks")
    if (by_id["lookup_left"]["handler"] != "local_rag"
            or by_id["lookup_right"]["handler"] != "local_rag"
            or by_id["join_evidence"]["handler"] != "join_evidence"):
        raise LearningPlanError("invalid_join_task")
    for task in tasks:
        deps = task.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(dep, str) or dep not in by_id for dep in deps):
            raise LearningPlanError("missing_dependency")
        if len(deps) != len(set(deps)):
            raise LearningPlanError("duplicate_dependency")
    if set(by_id["join_evidence"]["depends_on"]) != {"lookup_left", "lookup_right"}:
        raise LearningPlanError("invalid_join_dependencies")
    ordered: list[dict[str, Any]] = []
    remaining = dict(by_id)
    while remaining:
        ready = next((task for task in tasks if task["id"] in remaining
                      and all(dep in {item["id"] for item in ordered} for dep in task["depends_on"])), None)
        if ready is None:
            raise LearningPlanError("cyclic_dependencies")
        ordered.append(ready)
        remaining.pop(ready["id"])
    return ordered
