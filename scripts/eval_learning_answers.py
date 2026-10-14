"""Run an answer-level diagnostic on real workflow outputs with a scripted model.

No provider calls. Facet checks are literal and are NOT semantic accuracy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path[:0] = [str(WORKBENCH / "src"), str(WORKBENCH)]

from reasoning_agent_template.answer_eval import score_case  # noqa: E402
from reasoning_agent_template.learning import LearningAssistant  # noqa: E402
from tests.test_learning_mvp import ScriptedLearningClient  # noqa: E402


def corpus_hash(corpus: Path) -> str:
    digest = hashlib.sha256()
    for source in sorted(corpus.rglob("*")):
        if source.is_file():
            digest.update(source.relative_to(corpus).as_posix().encode("utf-8"))
            digest.update(source.read_bytes())
    return digest.hexdigest()


def main() -> int:
    rubric = json.loads((WORKBENCH / "evals" / "learning_answer_probe_v1.json").read_text(encoding="utf-8"))
    source = WORKBENCH / "learning_mvp" / "knowledge"
    actual_hash = corpus_hash(source)
    if actual_hash != rubric["frozen_corpus_sha256"]:
        raise RuntimeError("corpus changed; revise and review the rubric before replay")
    rows = []
    with tempfile.TemporaryDirectory() as temporary:
        for case in rubric["cases"]:
            workspace = Path(temporary) / case["id"]
            shutil.copytree(source, workspace / "knowledge")
            client = ScriptedLearningClient()
            result = LearningAssistant(workspace, client=client).ask(case["question"], thread_id="probe")
            rows.append(score_case(case, result, list(client.calls)))
    answered = [row for row in rows if row["expected_decision"] == "answered"]
    reviewed = [row for row in rows if row["expected_decision"] == "review_withheld"]
    stopped = [row for row in rows if row["expected_decision"].startswith("abstained")]
    report = {
        "rubric_status": rubric["label_status"],
        "corpus_sha256": actual_hash,
        "model": "offline-script",
        "real_qwen_calls": 0,
        "cases": len(rows),
        "decision_matches": sum(row["decision_match"] for row in rows),
        "qualified_anchor_cases": sum(all(row["qualified_anchor_hits"]) for row in [*answered, *reviewed]),
        "evidence_expected_cases": len(answered) + len(reviewed),
        "answered_cases": len(answered),
        "literal_answer_proxy_passes": sum(row["proxy_pass"] for row in answered),
        "strict_review_withheld": sum(row["proxy_pass"] for row in reviewed),
        "correct_stop_boundaries": sum(row["proxy_pass"] for row in stopped),
        "stop_cases": len(stopped),
        "semantic_accuracy_measured": False,
        "rows": rows,
    }
    target = ROOT / "artifacts" / "analysis" / "learning_answer_probe.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(target), **{key: value for key, value in report.items() if key != "rows"}},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
