"""No-API walkthrough: scripted models, real workflow, retrieval and persistence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
sys.path[:0] = [str(WORKBENCH / "src"), str(WORKBENCH)]

from reasoning_agent_template.learning import LearningAssistant  # noqa: E402
from reasoning_agent_template.learning_notes import LearningNoteStore  # noqa: E402
from reasoning_agent_template.learning_sessions import LearningSessionStore  # noqa: E402
from tests.test_learning_mvp import CompleteLearningReviewClient, ReviewedLearningClient  # noqa: E402

CASES = (
    {"case": "hash_concept", "question": "什么是哈希冲突？", "decision": "answered", "path": "guided",
     "answer_expectation": "两个不同的键映射到同一槽位，说明需要处理冲突。", "anchors": ["不同的键", "槽位"]},
    {"case": "tree_concept", "question": "二叉树是什么？", "decision": "answered", "path": "guided",
     "answer_expectation": "每个结点至多两个孩子；不自动保证有序或平衡。", "anchors": ["最多", "不保证"]},
    {"case": "bounded_comparison", "question": "哈希表和二叉搜索树有什么区别？",
     "decision": "answered", "path": "guided", "answer_expectation": "区分精确查找和有序范围查询，并说明条件。",
     "anchors": ["精确查找", "范围查询", "冲突"]},
    {"case": "strict_comparison", "question": "哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。",
     "decision": "answered", "path": "deep", "answer_expectation": "否定绝对结论，分别说明精确查找、范围查询与退化边界。",
     "anchors": ["不一定", "精确查找", "范围查询", "最坏情况"]},
    {"case": "outside_corpus", "question": "请解释 ZxqvPrime-99 的内部缓存协议。",
     "decision": "abstained_no_evidence", "path": "guided", "answer_expectation": "止答，不调用 Worker。", "anchors": []},
    {"case": "protected_action", "question": "请删除生产环境数据。", "decision": "blocked", "path": "deep",
     "answer_expectation": "保护性 Gate deny，不执行删除、不调用 Worker。", "anchors": []},
)


class DemoClient:
    """Observe actual prompts and delegate responses to explicit positive fixtures."""

    def __init__(self, *, strict: bool = False):
        self.delegate = CompleteLearningReviewClient() if strict else ReviewedLearningClient()
        self.model = self.delegate.model
        self.route_history = []
        self.skill_loaded = False

    @property
    def calls(self):
        return self.delegate.calls

    def chat(self, messages, **kwargs):
        text = "\n".join(message.content for message in messages)
        if "ROUTING_DECISION_JSON" in text:
            self.route_history = json.loads(
                messages[-1].content.split("短期记忆 JSON:\n", 1)[1].split("\n\n长期记忆 JSON:", 1)[0],
            )
        elif all(marker not in text for marker in ("REVIEW_DECISION_JSON", "OUTPUT_REVIEW_JSON")):
            self.skill_loaded = "已审批教学 Skill" in messages[0].content
        return self.delegate.chat(messages, **kwargs)


def question_step(workspace: Path, case: dict, thread: str) -> dict:
    client = DemoClient(strict=case["case"] == "strict_comparison")
    with patch("reasoning_agent_template.learning.qwen_client_from_env",
               side_effect=AssertionError("offline walkthrough must never create a Qwen client")):
        payload = LearningAssistant(workspace, client=client).ask(case["question"], thread_id=thread)
    answered = case["decision"] == "answered"
    expected_calls = ["route", "reviewer", *(["worker", "output_reviewer"] if answered else [])]
    expected_gate = "deny" if case["decision"] == "blocked" else "allow"
    assert payload["learning"]["decision"] == case["decision"], (case["case"], payload["learning"]["decision"])
    assert payload["learning"]["path"] == case["path"]
    assert payload["gates"]["decisions"][-1]["status"] == expected_gate
    assert client.calls == expected_calls, (case["case"], client.calls)
    if answered:
        assert payload["output_release"]["status"] == "released_model_reviewed"
        assert payload["learning"]["sources"] and all(item["original_url"] for item in payload["learning"]["sources"])
        assert all(term in payload["answer"] for term in case["anchors"])
    if case["case"] == "bounded_comparison":
        plan = payload["workflow"]["execution_plan"]
        assert plan["status"] == "completed" and len(plan["tasks"]) == 3
        assert [task["query"] for task in plan["tasks"][:2]] == ["哈希表", "二叉搜索树"]
    snapshot = LearningSessionStore(workspace / "sessions").load(thread)
    assert snapshot.messages[-1]["content"] == payload["answer"]
    return {
        "case": case["case"], "question": case["question"], "expected_decision": case["decision"],
        "answer_expectation": case["answer_expectation"], "path": payload["learning"]["path"],
        "decision": payload["learning"]["decision"], "gate": expected_gate,
        "output_release": payload["output_release"]["status"], "model_calls": client.calls,
        "answer": payload["answer"], "sources": payload["learning"]["sources"],
        "stage_trace": payload["state_machine"]["trace"], "skill_loaded": client.skill_loaded,
        "route_history_users": [turn["user"] for turn in client.route_history],
        "saved_user_turns": sum(message["role"] == "user" for message in snapshot.messages),
        "payload": payload,
    }


# Real CLI commands launch fresh interpreters. Block the lazy model factory in
# those interpreters too: an accidental AI call must fail before any network I/O.
CLI_BOOTSTRAP = """
import runpy, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path.cwd() / 'workbench/deepreason/src'))
sys.argv[0] = 'run_learning.py'
with patch('reasoning_agent_template.learning.qwen_client_from_env', side_effect=AssertionError('offline CLI must not call Qwen')):
    runpy.run_path('run_learning.py', run_name='__main__')
"""
SESSION_BOOTSTRAP = """
import json, sys
from pathlib import Path
from scripts.learning_mvp_demo import CASES, question_step
print(json.dumps(question_step(Path(sys.argv[1]), CASES[0], 'resume-demo'), ensure_ascii=False))
"""


def _process(code: str, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", "-c", code, *arguments], cwd=ROOT,
                          capture_output=True, encoding="utf-8", timeout=45,
                          creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)


def run_demo(workspace: Path) -> dict:
    # Never reset a real session or notes database; each run owns a new directory.
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    shutil.copytree(WORKBENCH / "learning_mvp" / "knowledge", workspace / "knowledge")
    rows = [question_step(workspace, case, f"six-{case['case']}") for case in CASES]
    assert all(not LearningNoteStore(workspace).list_notes(f"six-{case['case']}")["notes"] for case in CASES)
    commands = []

    def cli(step: str, *arguments: str, expected_code: int = 0, error: str = "") -> dict:
        args = ["--workspace", str(workspace), "--thread", "notes-demo", *arguments]
        result = _process(CLI_BOOTSTRAP, args)
        assert result.returncode == expected_code, (step, result.returncode, result.stdout, result.stderr)
        assert not result.stderr, (step, result.stderr)
        if error:
            assert error in result.stdout, (step, result.stdout)
        value = json.loads(result.stdout) if not error else {"error": error}
        commands.append({"step": step, "arguments": args, "exit_code": result.returncode,
                         "stdout": result.stdout.strip(), "result": value})
        return value

    session_first = question_step(workspace, CASES[1], "resume-demo")
    session_second = question_step(workspace, CASES[0], "resume-demo")
    restarted = _process(SESSION_BOOTSTRAP, [str(workspace)])
    assert restarted.returncode == 0 and not restarted.stderr, restarted.stderr
    session_third = json.loads(restarted.stdout)
    assert session_third["route_history_users"] == [CASES[1]["question"], CASES[0]["question"]]
    assert session_third["saved_user_turns"] == 3
    assert session_first["route_history_users"] == []

    cli("empty_notes", "--notes")
    body = "复习哈希冲突：不同的键可能映射到同一槽位。"
    created = cli("create_note", "--save-note", body, "--operation-id", "note-1", "--expected-version", "0")
    replayed = cli("replay_note", "--save-note", body, "--operation-id", "note-1", "--expected-version", "0")
    assert created["status"] == "created" and replayed["status"] == "replayed"
    assert created["note_id"] == replayed["note_id"]
    receipt = cli("receipt_after_restart", "--note-receipt", "note-1")
    assert receipt["note_id"] == created["note_id"]
    cli("reject_changed_body", "--save-note", "changed", "--operation-id", "note-1", "--expected-version", "1",
        expected_code=2, error="operation_id_reused_with_different_note")
    cli("reject_stale_note_version", "--save-note", body, "--operation-id", "note-2", "--expected-version", "0",
        expected_code=2, error="stale_thread_version")
    notes = cli("one_note_after_retries", "--notes")
    assert notes["version"] == 1 and len(notes["notes"]) == 1
    assert not LearningNoteStore(workspace).list_notes("other-thread")["notes"]

    cli("explicit_feedback", "--save-note", "比较题请先说明适用条件和前提，再解释两者差异。",
        "--operation-id", "feedback-1", "--expected-version", "1")
    candidate = cli("propose_skill", "--skill-propose-from-note", "feedback-1")
    stale = cli("propose_another_pending_skill", "--skill-propose-from-note", "feedback-1")
    baseline = cli("candidate_not_active", "--skill-status")
    assert baseline["version"] == 0 and candidate["status"] == "proposed"
    before = question_step(workspace, CASES[2], "skill-before")
    assert not before["skill_loaded"]
    cli("reject_wrong_candidate_hash", "--skill-approve", candidate["candidate_id"], "--candidate-hash", "wrong",
        expected_code=2, error="candidate_hash_mismatch")
    applied = cli("approve_skill", "--skill-approve", candidate["candidate_id"],
                  "--candidate-hash", candidate["content_hash"])
    assert applied["version"] == 1 and applied["revision"] == 1
    after = question_step(workspace, CASES[2], "skill-after")
    assert after["skill_loaded"]
    cli("reject_old_base", "--skill-approve", stale["candidate_id"], "--candidate-hash", stale["content_hash"],
        expected_code=2, error="base_version_changed")
    cli("reject_wrong_rollback_hash", "--skill-rollback", "0", "--expected-current-hash", "wrong",
        expected_code=2, error="active_hash_mismatch")
    restored = cli("rollback_skill", "--skill-rollback", "0", "--expected-current-hash", applied["content_hash"])
    assert restored["version"] == 0 and restored["revision"] == 2
    assert restored["content_hash"] == stale["base_hash"]
    cli("reject_old_base_after_rollback", "--skill-approve", stale["candidate_id"],
        "--candidate-hash", stale["content_hash"], expected_code=2, error="base_version_changed")
    rolled_back = question_step(workspace, CASES[2], "skill-rolled-back")
    assert not rolled_back["skill_loaded"]
    final_notes = cli("final_notes", "--notes")
    final_skill = cli("final_skill", "--skill-status")
    assert len(final_notes["notes"]) == 2 and final_skill["version"] == 0
    assert final_skill["revision"] == 2

    report = {
        "kind": "offline_scripted_application_walkthrough", "status": "passed", "real_qwen_calls": 0,
        "scope": "真实工作流/检索/存储/跨进程命令；模型回答与审查为固定脚本，未测语义准确率或教学收益。",
        "workspace": str(workspace), "six_cases_passed": len(rows), "cases": rows,
        "corpus_file_sha256": {source.name: hashlib.sha256(source.read_bytes()).hexdigest()
                               for source in sorted((workspace / "knowledge").iterdir()) if source.is_file()},
        "session": {"turns": [session_first, session_second, session_third], "process_restart_verified": True},
        "notes": {"first_note_id": created["note_id"], "after_replay_count": len(notes["notes"]),
                  "final_count_including_explicit_feedback": len(final_notes["notes"]), "automatic_note_writes": 0},
        "skill": {"candidate": candidate, "initial": baseline, "applied": applied, "restored": restored,
                  "prompt_runs": [before, after, rolled_back], "final": final_skill},
        "commands": commands,
    }
    all_questions = [*rows, session_first, session_second, session_third, before, after, rolled_back]
    report["scripted_model_calls"] = sum(len(row["model_calls"]) for row in all_questions)
    (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (workspace / "README.md").write_text(render_walkthrough(report), encoding="utf-8")
    return report


def render_walkthrough(report: dict) -> str:
    lines = ["# 学习助手离线操作结果", "", report["scope"], "", "## 六道代表题", ""]
    for row in report["cases"]:
        lines.extend([f"### {row['case']}：{row['question']}", "", f"预期：{row['answer_expectation']}", "",
                      row["answer"], "", f"实际：{row['path']} / {row['decision']} / Gate {row['gate']}；脚本调用 {len(row['model_calls'])}。", ""])
        lines.extend(f"- 来源：{item['original_url']}，{item['locator']}" for item in row["sources"])
        lines.append("")
    lines.extend(["## 状态闭环", "", "- 新进程第三轮实际收到前两轮问题，最终保存三轮。",
                  "- 同一笔记重复提交后仍一条；改正文和旧版本均被拒绝；显式反馈另算第二条笔记。",
                  "- Skill 候选未生效，批准后加载提示，回退后停止加载；旧候选在回退后仍被拒绝。",
                  "- 未证明 Skill 改善答案；这里核对实际提示加载和状态边界。", "",
                  "## 实际命令（每条均在新进程执行）", "",
                  "下列命令已执行，不要在这份已完成的演示目录重新执行写命令。重跑演示会创建新目录。", ""])
    for command in report["commands"]:
        arguments = " ".join('"' + item.replace('"', '`"') + '"' for item in command["arguments"])
        lines.extend([f"### {command['step']}（退出码 {command['exit_code']}）", "", "```powershell",
                      f".\\.venv\\Scripts\\python.exe run_learning.py {arguments}", "```", "", "```text",
                      command["stdout"], "```", ""])
    lines.extend([f"脚本模型调用总数：{report['scripted_model_calls']}；真实千问：0。", "",
                  "完整节点产物、事件与耗时见同目录 report.json；耗时只代表本地脚本运行。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="无 API 的六题、会话、笔记和 Skill 演示；每次保留独立结果目录。")
    parser.add_argument("--json", action="store_true", help="仅输出结果摘要 JSON")
    args = parser.parse_args()
    label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    workspace = ROOT / "artifacts" / "demos" / f"learning-{label}"
    report = run_demo(workspace)
    latest = ROOT / "artifacts" / "analysis" / "learning_mvp_offline.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps({"report": str(workspace / "report.json"), "walkthrough": str(workspace / "README.md"),
                          "passed": report["six_cases_passed"], "real_qwen_calls": 0,
                          "scripted_model_calls": report["scripted_model_calls"]}, ensure_ascii=False, indent=2))
    else:
        print("离线演示：模型回答和复核为固定脚本，工作流、检索、文件与数据库实际执行。\n")
        for row in report["cases"]:
            print(f"你> {row['question']}\n回答：{row['answer']}\n结果：{row['decision']}；脚本调用 {len(row['model_calls'])}\n")
        print("六题 6/6；新进程恢复 3 轮；笔记重放仍 1 条；Skill 提出→审批→回退通过。")
        print("旧候选在回退后仍被拒绝；真实千问 0 次。")
        print(f"逐步操作与实际回执：{workspace / 'README.md'}\n完整轨迹：{workspace / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
