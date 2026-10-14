"""Produce a synthetic, no-API learning-path trace for teaching and regression."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path.insert(0, str(WORKBENCH / "src"))
sys.path.insert(0, str(WORKBENCH))

from reasoning_agent_template.learning import LearningAssistant  # noqa: E402
from tests.test_learning_mvp import ScriptedLearningClient  # noqa: E402


CASES = [
    ("concept", "什么是哈希冲突？"),
    ("conditional", "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。"),
    ("outside_corpus", "请解释 ZxqvPrime-99 的内部缓存协议。"),
]


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory(prefix="deepreason-learning-demo-") as temp:
        workspace = Path(temp)
        shutil.copytree(WORKBENCH / "learning_mvp" / "knowledge", workspace / "knowledge")
        client = ScriptedLearningClient()
        assistant = LearningAssistant(workspace, client=client)
        for case_id, question in CASES:
            before = len(client.calls)
            payload = assistant.ask(question, thread_id="demo-learner")
            rows.append({
                "case": case_id,
                "question": question,
                "path": payload["learning"]["path"],
                "decision": payload["learning"]["decision"],
                "route": payload["routing"]["decision"],
                "gate": payload["gates"]["decisions"][-1]["status"],
                "qualified_evidence_count": len(payload["evidence"]["qualified_evidence_ids"]),
                "source_urls": [item["original_url"] for item in payload["learning"]["sources"]],
                "stage_trace": payload["state_machine"]["trace"],
                "model_calls": client.calls[before:],
                "output_release": payload["output_release"]["status"],
                "answer": payload["answer"],
            })
    report = {
        "kind": "offline_scripted_harness_trace",
        "real_qwen_calls": 0,
        "note": "Scripted model answers demonstrate routing and gates only; they do not measure teaching quality.",
        "cases": rows,
    }
    destination = ROOT / "artifacts" / "analysis" / "learning_mvp_offline.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(destination),
        "cases": [{"case": row["case"], "path": row["path"], "decision": row["decision"], "gate": row["gate"],
                   "qualified_evidence_count": row["qualified_evidence_count"], "model_calls": row["model_calls"]}
                  for row in rows],
        "real_qwen_calls": 0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
