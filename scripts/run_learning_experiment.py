"""Plan, run, and manually score a bounded Skill comparison. Defaults to plan only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path[:0] = [str(WORKBENCH / "src"), str(WORKBENCH)]

from reasoning_agent_template.learning import (  # noqa: E402
    BudgetedQwenClient, LearningAssistant, MAX_QWEN_CALLS, USAGE_DB, qwen_client_from_env,
)
from reasoning_agent_template.learning_experiment import (  # noqa: E402
    ExperimentClient, call_summary, content_hash, make_review_packet, score_manual_review,
    terminal_model_failures,
)
from reasoning_agent_template.learning_notes import LearningNoteStore  # noqa: E402
from reasoning_agent_template.learning_skill import LearningSkillStore  # noqa: E402
from reasoning_agent_template.llm import MissingApiKeyError  # noqa: E402


CASE_IDS = ("hash_tree_range", "missing_comparison", "hash_collision")
MAX_EXPERIMENT_CALLS = 32  # An imposed cap; unusual strict routes can exhaust it before all pairs finish.


def corpus_hash(corpus: Path) -> str:
    digest = hashlib.sha256()
    for source in sorted(corpus.rglob("*")):
        if source.is_file():
            digest.update(source.relative_to(corpus).as_posix().encode("utf-8"))
            digest.update(source.read_bytes())
    return digest.hexdigest()


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_sample(parent: Path, case: dict, variant: str, client: ExperimentClient, frozen: str) -> dict:
    workspace = parent / case["id"] / variant
    shutil.copytree(WORKBENCH / "learning_mvp" / "knowledge", workspace / "knowledge")
    spec = workspace / "configs" / "workflows" / "learning.workflow.json"
    spec.parent.mkdir(parents=True)
    shutil.copyfile(WORKBENCH / "learning_mvp" / "configs" / "workflows" / spec.name, spec)
    if corpus_hash(workspace / "knowledge") != frozen or (workspace / "sessions").exists():
        raise ValueError("experiment_initial_state_changed")
    notes = LearningNoteStore(workspace)
    notes.save(thread_id="feedback", operation_id="fb-1", expected_version=0,
               body="比较题请先说明适用条件和前提，再解释两者差异。")
    skill = LearningSkillStore(workspace)
    if variant == "approved":
        candidate = skill.propose_from_note(thread_id="feedback", operation_id="fb-1",
                                            feedback_kind="missing_preconditions")
        skill.approve(candidate["candidate_id"], expected_hash=candidate["content_hash"],
                      approved_by="explicit-experiment-command")
    start = len(client.calls)
    assistant = LearningAssistant(workspace, client=client)
    result = assistant.ask(case["question"], thread_id="experiment")
    calls = client.calls[start:]
    if client.blocked_reason:
        # The final Reviewer can catch provider exceptions and return a safe reply.
        # Such a run is an operational failure, not a valid quality comparison.
        raise ValueError("experiment_model_attempt_failed")
    if terminal_model_failures(calls):
        raise ValueError("experiment_terminal_model_failure")
    if corpus_hash(workspace / "knowledge") != frozen:
        raise ValueError("experiment_corpus_changed")
    saved = assistant.orchestrator.session_store.load("experiment")
    if saved.messages[-1]["content"] != result["answer"]:
        raise ValueError("experiment_session_mismatch")
    qualified = set(result["evidence"]["qualified_evidence_ids"])
    return {
        "run_id": result["run_id"], "answer": result["answer"],
        "decision": result["learning"]["decision"], "release": result["output_release"],
        "gate": result["gates"]["decisions"][-1]["status"],
        "trace": result["state_machine"]["trace"], "duration_ms": result["duration_ms"],
        "skill_content_hash": skill.active()["content_hash"],
        "qualified_evidence": [{
            "file": Path(chunk["source"]).name, "span": chunk["span"],
            "evidence_id": chunk["evidence_id"], "content_hash": chunk["content_hash"], "text": chunk["text"],
        } for chunk in result["rag"]["results"] if chunk["evidence_id"] in qualified],
        "calls": calls, "call_summary": call_summary(calls),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="执行脚本模型实验，不发真实请求")
    mode.add_argument("--qwen", action="store_true", help="显式执行真实千问实验；仍受全库 100 次上限")
    mode.add_argument("--score", type=Path, help="核对并汇总已填写的 review.json，不调用模型")
    parser.add_argument("--max-calls", type=int, default=MAX_EXPERIMENT_CALLS)
    args = parser.parse_args(argv)
    if args.score:
        path = args.score.resolve()
        path.relative_to((ROOT / "artifacts").resolve())
        folder = path.parent
        experiment = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        packet = json.loads((folder / "review_packet.json").read_text(encoding="utf-8"))
        review = json.loads(path.read_text(encoding="utf-8"))
        score = score_manual_review(experiment, packet, review)
        save_json(folder / "scorecard.json", score)
        print(json.dumps(score, ensure_ascii=False, indent=2))
        return 0
    if not 1 <= args.max_calls <= MAX_EXPERIMENT_CALLS:
        parser.error("max-calls must be between 1 and 32")
    rubric = json.loads((WORKBENCH / "evals" / "learning_answer_probe_v1.json").read_text(encoding="utf-8"))
    cases = [next(case for case in rubric["cases"] if case["id"] == case_id) for case_id in CASE_IDS]
    frozen = corpus_hash(WORKBENCH / "learning_mvp" / "knowledge")
    if frozen != rubric["frozen_corpus_sha256"]:
        raise ValueError("frozen_experiment_corpus_changed")
    if not (args.offline or args.qwen):
        print(json.dumps({"mode": "plan_only", "pairs": len(cases), "questions": [case["question"] for case in cases],
                          "script_profile_attempts": 16, "four_roles_two_attempts_upper_bound": 48,
                          "experiment_attempt_cap": args.max_calls,
                          "real_qwen_calls": 0, "next": "--offline or explicit --qwen"}, ensure_ascii=False, indent=2))
        return 0
    before = None
    if args.qwen:
        before = BudgetedQwenClient.calls_used_at(USAGE_DB)
        if before + args.max_calls > MAX_QWEN_CALLS:
            raise ValueError("not_enough_repository_call_allowance")
        backend = qwen_client_from_env()
    else:
        from tests.test_learning_mvp import ScriptedLearningClient
        backend = ScriptedLearningClient()
    client = ExperimentClient(backend, max_calls=args.max_calls)
    folder = ROOT / "artifacts" / "experiments" / f"skill_{uuid.uuid4().hex[:12]}"
    folder.mkdir(parents=True)
    package = WORKBENCH / "src" / "reasoning_agent_template"
    experiment = {
        "experiment_id": folder.name, "status": "running", "source": "qwen" if args.qwen else "offline-script",
        "corpus_sha256": frozen,
        "workflow_sha256": hashlib.sha256((WORKBENCH / "learning_mvp" / "configs" / "workflows" /
                                             "learning.workflow.json").read_bytes()).hexdigest(),
        "code_sha256": content_hash({path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in sorted(package.rglob("*.py"))}),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "max_forwarded_attempts": args.max_calls, "cases": [],
        "repository_reservations_before": before,
    }
    try:
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases:
                row = {"id": case["id"], "question": case["question"],
                       "rubric": {"answer_facets": case["answer_facets"], "source_anchors": case["source_anchors"]}}
                experiment["cases"].append(row)
                # Alternate order to limit a systematic timing/order bias.
                variants = ("baseline", "approved") if len(experiment["cases"]) % 2 else ("approved", "baseline")
                for variant in variants:
                    row[variant] = run_sample(Path(temporary), case, variant, client, frozen)
                    save_json(folder / "manifest.json", experiment)
        experiment["status"] = "completed"
    except Exception as exc:
        experiment["status"] = "aborted"
        experiment["error_type"] = type(exc).__name__
        if isinstance(exc, ValueError) and str(exc) in {
            "experiment_model_attempt_failed", "experiment_terminal_model_failure", "experiment_corpus_changed",
            "experiment_session_mismatch", "experiment_initial_state_changed",
        }:
            experiment["error_code"] = str(exc)
    experiment["call_summary"] = call_summary(client.calls)
    experiment["calls"] = client.calls  # Keep failed attempts even if no run result was returned.
    experiment["rejected_calls"] = client.rejected_calls
    experiment["blocked_reason"] = client.blocked_reason
    experiment["repository_reservations_after"] = BudgetedQwenClient.calls_used_at(USAGE_DB) if args.qwen else None
    save_json(folder / "manifest.json", experiment)
    if experiment["status"] == "completed":
        packet, review = make_review_packet(experiment)
        save_json(folder / "review_packet.json", packet)
        save_json(folder / "review.json", review)
        save_json(folder / "scorecard.json", score_manual_review(experiment, packet, review))
    print(json.dumps({"folder": str(folder), "status": experiment["status"],
                      "source": experiment["source"], **experiment["call_summary"],
                      "rejected_calls": client.rejected_calls,
                      "manual_review": "pending" if experiment["status"] == "completed" else "not_created_due_to_abort",
                      "real_qwen_calls": 0 if args.offline else "see repository reservation counters"},
                     ensure_ascii=False, indent=2))
    return 0 if experiment["status"] == "completed" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        exit_code = main()
    except (ValueError, OSError, MissingApiKeyError) as exc:
        reason = "missing_model_configuration" if isinstance(exc, MissingApiKeyError) else str(exc)
        if not re.fullmatch(r"[a-z_]{1,80}", reason):
            reason = "invalid_experiment_input"
        print(json.dumps({"status": "not_started_or_invalid_review", "reason": reason,
                          "error_type": type(exc).__name__}, ensure_ascii=False))
        exit_code = 2
    raise SystemExit(exit_code)
