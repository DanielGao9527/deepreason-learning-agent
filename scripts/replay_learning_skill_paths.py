"""Paired fresh-workspace replay for the approved teaching skill; no paid model calls."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path.insert(0, str(WORKBENCH / "src"))
sys.path.insert(0, str(WORKBENCH))

from reasoning_agent_template.learning import LearningAssistant  # noqa: E402
from reasoning_agent_template.learning_notes import LearningNoteStore  # noqa: E402
from reasoning_agent_template.learning_skill import LearningSkillStore  # noqa: E402
from reasoning_agent_template.workflow import TemplateCoordinator, WorkflowContractError  # noqa: E402
from tests.test_learning_mvp import ScriptedLearningClient  # noqa: E402


FROZEN_BASE_CORPUS_SHA256 = "36b913d8c5186a6bb6205ad1a27feee9033f896501a6a98066449c45fc8c8cc0"
FROZEN_COMPARISON_CORPUS_SHA256 = "5095246be97a2c4b6a874653fdfcffe0b88deded38e26025b87aed083f2d6500"


CASES = (
    ("concept", "什么是哈希冲突？", "answered", False),
    ("comparison_new", "哈希表和二叉搜索树有什么区别？", "answered", True),
    ("comparison_missing", "满二叉树和完全二叉树的定义有什么区别？", "abstained_incomplete_evidence", False),
    ("outside_corpus", "请解释 ZxqvPrime-99 的内部缓存协议。", "abstained_no_evidence", False),
    ("protected_action", "请删除生产环境数据。", "blocked", False),
    ("strict_question", "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。", "answered", False),
    ("invalid_handoff", "什么是哈希冲突？", "handoff_rejected", False),
)


class CapturingClient(ScriptedLearningClient):
    def __init__(self):
        super().__init__()
        self.worker_skill_loaded = False

    def chat(self, messages, *, temperature, max_tokens):
        prompt = "\n".join(message.content for message in messages)
        if all(marker not in prompt for marker in
               ("ROUTING_DECISION_JSON", "REVIEW_DECISION_JSON", "OUTPUT_REVIEW_JSON")):
            self.worker_skill_loaded = "已审批教学 Skill" in messages[0].content
        return super().chat(messages, temperature=temperature, max_tokens=max_tokens)


def corpus_hash(corpus: Path) -> str:
    digest = hashlib.sha256()
    for source in sorted(corpus.rglob("*")):
        if source.is_file():
            digest.update(source.relative_to(corpus).as_posix().encode("utf-8"))
            digest.update(source.read_bytes())
    return digest.hexdigest()


def replay(parent: Path, case: tuple[str, str, str, bool], *, active: bool) -> dict:
    case_id, question, expected, extra_source = case
    workspace = parent / case_id / ("approved" if active else "baseline")
    shutil.copytree(WORKBENCH / "learning_mvp" / "knowledge", workspace / "knowledge")
    if extra_source:
        (workspace / "knowledge" / "comparison_holdout.md").write_text(
            "哈希表：通过哈希函数定位键，平均精确查找通常较快。"
            "二叉搜索树：按键顺序组织结点，支持有序遍历与范围查询。",
            encoding="utf-8",
        )
    source_hash = corpus_hash(workspace / "knowledge")
    frozen = FROZEN_COMPARISON_CORPUS_SHA256 if extra_source else FROZEN_BASE_CORPUS_SHA256
    if source_hash != frozen:
        raise AssertionError(f"{case_id}: corpus differs from the frozen replay version")
    note_store = LearningNoteStore(workspace)
    note_store.save(thread_id="feedback", operation_id="fb-1",
                    body="比较题请先说明适用条件和前提，再解释两者差异。", expected_version=0)
    skill = LearningSkillStore(workspace)
    if active:
        candidate = skill.propose_from_note(thread_id="feedback", operation_id="fb-1",
                                            feedback_kind="missing_preconditions")
        skill.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                      approved_by="explicit-replay-command")
    if (workspace / "sessions").exists():
        raise AssertionError("replay must start without a session")
    client = CapturingClient()
    assistant = LearningAssistant(workspace, client=client)
    if case_id == "invalid_handoff":
        original_retrieve = TemplateCoordinator._retrieve

        def corrupt_handoff(coordinator, state):
            original_retrieve(coordinator, state)
            if not state.retrieval_results:
                raise AssertionError("fault injection requires a retrieved candidate")
            state.retrieval_results[0] = replace(state.retrieval_results[0], evidence_id="ev_missing")

        with patch.object(TemplateCoordinator, "_retrieve", corrupt_handoff):
            try:
                assistant.ask(question, thread_id="replay")
            except WorkflowContractError as exc:
                if exc.code != "evidence_missing":
                    raise
            else:
                raise AssertionError("corrupt handoff must be rejected")
        failures = list((workspace / "local_state" / "failures").glob("*.json"))
        if len(failures) != 1 or (workspace / "sessions" / "replay" / "snapshot.json").exists():
            raise AssertionError("failure must have one trace and no published session")
        trace = json.loads(failures[0].read_text(encoding="utf-8"))
        if trace["terminal_status"] != expected or trace["reason_code"] != "evidence_missing":
            raise AssertionError("wrong failure terminal")
        return {
            "decision": trace["terminal_status"], "release": "not_reached", "gate": "not_reached",
            "model_calls": list(client.calls), "worker_skill_loaded": client.worker_skill_loaded,
            "stage_trace": trace["completed_stages"], "corpus_sha256": source_hash,
            "skill_version": skill.active()["version"], "session_saved": False,
            "run_id": trace["run_id"], "failure_reason_code": trace["reason_code"], "duration_ms": None,
        }
    result = assistant.ask(question, thread_id="replay")
    saved = assistant.orchestrator.session_store.load("replay")
    decision = result["learning"]["decision"]
    if decision != expected or saved.messages[-1]["content"] != result["answer"]:
        raise AssertionError(f"{case_id}: outcome or saved answer mismatch: {decision}")
    return {
        "decision": decision,
        "release": result["output_release"]["status"],
        "gate": result["gates"]["decisions"][-1]["status"],
        "model_calls": list(client.calls),
        "worker_skill_loaded": client.worker_skill_loaded,
        "stage_trace": list(result["state_machine"]["trace"]),
        "corpus_sha256": source_hash,
        "skill_version": skill.active()["version"],
        "session_saved": True,
        "run_id": result["run_id"],
        "failure_reason_code": None,
        "duration_ms": result["duration_ms"],
    }


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as temporary:
        parent = Path(temporary)
        for case in CASES:
            baseline = replay(parent, case, active=False)
            approved = replay(parent, case, active=True)
            case_id = case[0]
            if baseline["corpus_sha256"] != approved["corpus_sha256"]:
                raise AssertionError(f"{case_id}: corpus changed between variants")
            for key in ("decision", "release", "gate", "model_calls", "stage_trace", "session_saved"):
                if baseline[key] != approved[key]:
                    raise AssertionError(f"{case_id}: unexpected change in {key}")
            expected_trigger = case_id == "comparison_new"
            if baseline["worker_skill_loaded"] or approved["worker_skill_loaded"] != expected_trigger:
                raise AssertionError(f"{case_id}: skill activation boundary changed")
            rows.append({"case": case_id, "expected_decision": case[2],
                         "baseline": baseline, "approved": approved})
    report = {
        "paired_cases": len(rows),
        "expected_decisions_passed": sum(
            row["baseline"]["decision"] == row["expected_decision"] and
            row["approved"]["decision"] == row["expected_decision"] for row in rows
        ),
        "unexpected_control_flow_changes": 0,
        "approved_skill_loaded_cases": sum(row["approved"]["worker_skill_loaded"] for row in rows),
        "model_call_delta_total": sum(len(row["approved"]["model_calls"]) -
                                      len(row["baseline"]["model_calls"]) for row in rows),
        "real_qwen_calls": 0,
        "answer_quality_measured": False,
        "frozen_base_corpus_sha256": FROZEN_BASE_CORPUS_SHA256,
        "frozen_comparison_corpus_sha256": FROZEN_COMPARISON_CORPUS_SHA256,
        "cases": rows,
    }
    target = ROOT / "artifacts" / "analysis" / "learning_skill_paired_replay.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(target), **{key: value for key, value in report.items() if key != "cases"}},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
