"""Offline old/candidate/overbroad teaching-skill comparison from a fresh note."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench" / "deepreason" / "src"))

from reasoning_agent_template.learning_notes import LearningNoteStore  # noqa: E402
from reasoning_agent_template.learning_skill import LearningSkillError, LearningSkillStore  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        LearningNoteStore(workspace).save(
            thread_id="fixture", operation_id="feedback-1",
            body="比较题缺少成立前提，我希望先说明条件再说差异。", expected_version=0,
        )
        store = LearningSkillStore(workspace)
        good = store.propose_from_note(
            thread_id="fixture", operation_id="feedback-1", feedback_kind="missing_preconditions",
        )
        broad = store.propose_from_note(
            thread_id="fixture", operation_id="feedback-1", feedback_kind="missing_preconditions",
            trigger="any",
        )
        rejected = False
        try:
            store.approve(broad["candidate_id"], expected_hash=broad["content_hash"],
                          approved_by="explicit-fixture-command")
        except LearningSkillError as exc:
            rejected = str(exc) == "candidate_evaluation_failed"
        if not rejected or store.active()["version"] != 0:
            raise AssertionError("overbroad candidate must not activate")
        applied = store.approve(good["candidate_id"], expected_hash=good["content_hash"],
                                approved_by="explicit-fixture-command")
        active_trigger = bool(store.instruction_for("满二叉树和完全二叉树有什么区别？", evidence_ready=True))
        withheld_without_evidence = not bool(store.instruction_for(
            "满二叉树和完全二叉树有什么区别？", evidence_ready=False,
        ))
        withheld_for_concept = not bool(store.instruction_for("二叉树是什么？", evidence_ready=True))
        restored = store.rollback(0, expected_current_hash=applied["content_hash"],
                                  approved_by="explicit-fixture-command")
        if not all((active_trigger, withheld_without_evidence, withheld_for_concept,
                    restored["version"] == 0, not store.instruction_for(
                        "满二叉树和完全二叉树有什么区别？", evidence_ready=True))):
            raise AssertionError("skill activation or rollback boundary failed")
        report = {
            "evaluation_cases": good["evaluation"]["total"],
            "baseline_correct_triggers": sum(
                row["before"] == row["expected"] for row in good["evaluation"]["cases"]
            ),
            "bounded_candidate_correct_triggers": good["evaluation"]["passed"],
            "overbroad_candidate_correct_triggers": broad["evaluation"]["passed"],
            "overbroad_rejected": rejected,
            "explicit_approval_version": applied["version"],
            "rollback_version": restored["version"],
            "real_qwen_calls": 0,
            "scope": "fixed three-case trigger experiment; no answer-quality measurement",
        }
    target = ROOT / "artifacts" / "analysis" / "learning_skill_lifecycle.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(target), **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
