"""One versioned, explicitly approved teaching-skill experiment for comparison tasks."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from reasoning_agent_template.gates import GatePolicy
from reasoning_agent_template.learning_notes import LearningNoteStore
from reasoning_agent_template.models import EvidenceItem, utc_now


SKILL_ID = "comparison-preconditions"
BASE_HASH = hashlib.sha256(b"disabled-comparison-skill-v1").hexdigest()
INSTRUCTIONS = {
    "missing_preconditions": (
        "比较两个概念时，先列出比较成立的前提与适用范围，再解释差异；"
        "前提必须有本轮资料支持，缺证据就说明不足。"
    ),
}
EVAL_CASES = (
    ("positive", "满二叉树和完全二叉树有什么区别？", True, True),
    ("changed_precondition", "满二叉树和完全二叉树有什么区别？", False, False),
    ("negative", "二叉树是什么？", True, False),
)


class LearningSkillError(RuntimeError):
    """A candidate failed its evidence, evaluation, version, or approval boundary."""


def _applies(trigger: str, question: str, evidence_ready: bool) -> bool:
    if not evidence_ready:
        return False
    if trigger == "any":
        return True
    return trigger == "explicit_comparison" and bool(re.search(
        r".+(?:和|与).+(?:区别|不同|区分)", question,
    ))


def _content_hash(trigger: str, instruction: str) -> str:
    content = json.dumps({"trigger": trigger, "instruction": instruction},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _evaluate(old_trigger: str, new_trigger: str) -> dict[str, Any]:
    rows = [
        {"case": case_id, "expected": expected,
         "before": _applies(old_trigger, question, evidence_ready),
         "candidate": _applies(new_trigger, question, evidence_ready)}
        for case_id, question, evidence_ready, expected in EVAL_CASES
    ]
    return {"cases": rows, "passed": sum(row["candidate"] == row["expected"] for row in rows),
            "total": len(rows)}


class LearningSkillStore:
    """Candidate evaluation and hash-bound approval; local single-user workspace only."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.path = self.workspace_root / "local_state" / "learning_skill.sqlite3"

    @staticmethod
    def _schema(db: sqlite3.Connection) -> None:
        db.execute("CREATE TABLE IF NOT EXISTS versions ("
                   "version INTEGER PRIMARY KEY, content_hash TEXT NOT NULL, trigger TEXT NOT NULL, "
                   "instruction TEXT NOT NULL, approved_by TEXT NOT NULL, created_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), "
                   "active_version INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS candidates ("
                   "candidate_id TEXT PRIMARY KEY, base_hash TEXT NOT NULL, content_hash TEXT NOT NULL, "
                   "trigger TEXT NOT NULL, instruction TEXT NOT NULL, source_note_id TEXT NOT NULL, "
                   "source_body_hash TEXT NOT NULL, source_thread_id TEXT NOT NULL, "
                   "evaluation TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, "
                   "base_revision INTEGER)")
        db.execute("CREATE TABLE IF NOT EXISTS rollbacks ("
                   "id TEXT PRIMARY KEY, from_version INTEGER NOT NULL, to_version INTEGER NOT NULL, "
                   "approved_by TEXT NOT NULL, created_at TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO versions VALUES (0, ?, '', '', 'baseline', ?)",
                   (BASE_HASH, utc_now()))
        # A rollback restores content, but must not restore the approval epoch.
        # Legacy pending candidates have no reliable epoch and need reproposal.
        if "revision" not in {row[1] for row in db.execute("PRAGMA table_info(state)")}:
            db.execute("ALTER TABLE state ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")
        if "base_revision" not in {row[1] for row in db.execute("PRAGMA table_info(candidates)")}:
            db.execute("ALTER TABLE candidates ADD COLUMN base_revision INTEGER")
        db.execute("INSERT OR IGNORE INTO state (id, active_version, revision) VALUES (1, 0, 0)")

    @staticmethod
    def _active(db: sqlite3.Connection) -> dict[str, Any]:
        row = db.execute(
            "SELECT v.version, v.content_hash, v.trigger, v.instruction, s.revision FROM versions v "
            "JOIN state s ON s.active_version=v.version WHERE s.id=1",
        ).fetchone()
        if row[0] == 0:
            valid = row[1] == BASE_HASH and row[2] == row[3] == ""
        else:
            valid = _content_hash(row[2], row[3]) == row[1]
        if not valid:
            raise LearningSkillError("active_content_hash_mismatch")
        return {"version": row[0], "content_hash": row[1], "trigger": row[2], "instruction": row[3],
                "revision": row[4]}

    def active(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 0, "content_hash": BASE_HASH, "trigger": "", "instruction": "", "revision": 0}
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            self._schema(db)
            active = self._active(db)
            db.commit()
            return active

    def instruction_for(self, question: str, *, evidence_ready: bool) -> str:
        active = self.active()
        return active["instruction"] if _applies(active["trigger"], question, evidence_ready) else ""

    def propose_from_note(
        self, *, thread_id: str, operation_id: str, feedback_kind: str,
        trigger: str = "explicit_comparison",
    ) -> dict[str, Any]:
        if feedback_kind not in INSTRUCTIONS or trigger not in {"explicit_comparison", "any"}:
            raise LearningSkillError("unsupported_candidate_rule")
        notes = LearningNoteStore(self.workspace_root)
        receipt = notes.receipt(thread_id, operation_id)
        if receipt is None:
            raise LearningSkillError("source_note_not_found")
        source = next(note for note in notes.list_notes(thread_id)["notes"]
                      if note["note_id"] == receipt["note_id"])
        if "比较" not in source["body"] or not any(
            term in source["body"] for term in ("前提", "条件", "适用")
        ):
            raise LearningSkillError("source_note_not_comparison_feedback")
        instruction = INSTRUCTIONS[feedback_kind]
        content_hash = _content_hash(trigger, instruction)
        old = self.active()
        evaluation = _evaluate(old["trigger"], trigger)
        candidate_id = f"skill_{uuid.uuid4().hex[:16]}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._schema(db)
            current = self._active(db)
            if (current["content_hash"], current["revision"]) != (old["content_hash"], old["revision"]):
                raise LearningSkillError("active_version_changed_during_proposal")
            db.execute(
                "INSERT INTO candidates (candidate_id, base_hash, content_hash, trigger, instruction, "
                "source_note_id, source_body_hash, source_thread_id, evaluation, status, created_at, "
                "base_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)",
                (candidate_id, old["content_hash"], content_hash, trigger, instruction,
                 receipt["note_id"], hashlib.sha256(source["body"].encode("utf-8")).hexdigest(),
                 thread_id, json.dumps(evaluation, ensure_ascii=False), utc_now(), old["revision"]),
            )
            db.commit()
        return {"candidate_id": candidate_id, "base_hash": old["content_hash"], "base_revision": old["revision"],
                "content_hash": content_hash, "source_note_id": receipt["note_id"],
                "evaluation": evaluation, "status": "proposed"}

    def approve(self, candidate_id: str, *, expected_hash: str, approved_by: str | None) -> dict[str, Any]:
        if not approved_by or not approved_by.strip():
            raise LearningSkillError("explicit_approval_required")
        if not re.fullmatch(r"skill_[0-9a-f]{16}", candidate_id):
            raise LearningSkillError("invalid_candidate_id")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._schema(db)
            row = db.execute("SELECT base_hash, content_hash, trigger, instruction, evaluation, status, "
                             "source_note_id, source_body_hash, source_thread_id, base_revision "
                             "FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if row is None or row[5] != "proposed":
                raise LearningSkillError("candidate_not_pending")
            if row[1] != expected_hash:
                raise LearningSkillError("candidate_hash_mismatch")
            if _content_hash(row[2], row[3]) != row[1]:
                raise LearningSkillError("candidate_content_changed")
            source = next((note for note in LearningNoteStore(self.workspace_root).list_notes(row[8])["notes"]
                           if note["note_id"] == row[6]), None)
            if source is None or hashlib.sha256(source["body"].encode("utf-8")).hexdigest() != row[7]:
                raise LearningSkillError("candidate_source_changed")
            gate = GatePolicy(
                workspace_root=self.workspace_root,
                min_evidence_by_risk={"medium": 1},
                approval_required_actions={"update_skill"},
            ).evaluate(
                action="update_skill", risk_level="medium",
                evidence=[EvidenceItem(
                    id=row[6], source_type="explicit_learning_feedback", uri="local://learning-note",
                    locator=row[8], content_hash=row[7], summary="explicit comparison feedback",
                    confidence=1.0, collected_at=source["created_at"],
                )],
                target_path=self.path, approved_by=approved_by,
            )
            if gate.status != "allow":
                raise LearningSkillError("skill_update_gate_rejected")
            evaluation = json.loads(row[4])
            active = self._active(db)
            if row[9] is None:
                raise LearningSkillError("candidate_requires_reproposal")
            if active["content_hash"] != row[0] or active["revision"] != row[9]:
                raise LearningSkillError("base_version_changed")
            if evaluation != _evaluate(active["trigger"], row[2]):
                raise LearningSkillError("candidate_evaluation_changed")
            if evaluation["passed"] != evaluation["total"]:
                raise LearningSkillError("candidate_evaluation_failed")
            version = int(db.execute("SELECT MAX(version) FROM versions").fetchone()[0]) + 1
            db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?)",
                       (version, row[1], row[2], row[3], approved_by.strip(), utc_now()))
            db.execute("UPDATE state SET active_version=?, revision=revision+1 WHERE id=1", (version,))
            db.execute("UPDATE candidates SET status='applied' WHERE candidate_id=?", (candidate_id,))
            db.commit()
        return {"status": "applied", "version": version, "content_hash": row[1],
                "revision": active["revision"] + 1,
                "gate_decision": gate.to_dict()}

    def rollback(self, target_version: int, *, expected_current_hash: str,
                 approved_by: str | None) -> dict[str, Any]:
        if not approved_by or not approved_by.strip():
            raise LearningSkillError("explicit_approval_required")
        if type(target_version) is not int or target_version < 0 or not self.path.exists():
            raise LearningSkillError("invalid_target_version")
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._schema(db)
            current = self._active(db)
            if current["content_hash"] != expected_current_hash:
                raise LearningSkillError("active_hash_mismatch")
            target = db.execute("SELECT content_hash, trigger, instruction FROM versions WHERE version=?",
                                (target_version,)).fetchone()
            if target is None or target_version >= current["version"]:
                raise LearningSkillError("invalid_target_version")
            if target_version == 0:
                valid_target = target[0] == BASE_HASH and target[1] == target[2] == ""
            else:
                valid_target = _content_hash(target[1], target[2]) == target[0]
            if not valid_target:
                raise LearningSkillError("target_content_hash_mismatch")
            gate = GatePolicy(
                workspace_root=self.workspace_root,
                approval_required_actions={"update_skill"},
            ).evaluate(
                action="update_skill", risk_level="none", evidence=[],
                target_path=self.path, approved_by=approved_by,
            )
            if gate.status != "allow":
                raise LearningSkillError("skill_rollback_gate_rejected")
            db.execute("UPDATE state SET active_version=?, revision=revision+1 WHERE id=1", (target_version,))
            db.execute("INSERT INTO rollbacks VALUES (?, ?, ?, ?, ?)",
                       (uuid.uuid4().hex, current["version"], target_version, approved_by.strip(), utc_now()))
            db.commit()
        return {"status": "rolled_back", "version": target_version, "content_hash": target[0],
                "revision": current["revision"] + 1,
                "gate_decision": gate.to_dict()}
