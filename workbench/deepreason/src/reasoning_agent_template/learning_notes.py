"""Local learning notes with transactional replay and optimistic thread versions."""
from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from reasoning_agent_template.config import AgentConfig
from reasoning_agent_template.models import utc_now
from reasoning_agent_template.runtime import AgentRuntime, AgentRuntimeResult, RuntimeTool, ToolCall, ToolModelResponse


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class NoteConflictError(RuntimeError):
    """A duplicate operation changed arguments or a thread version went stale."""


class LearningNoteStore:
    """One SQLite transaction owns both the note side effect and its receipt."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.path = self.workspace_root / "local_state" / "learning_notes.sqlite3"

    def list_notes(self, thread_id: str) -> dict[str, Any]:
        thread_id = self._identifier(thread_id, "thread_id")
        if not self.path.exists():
            return {"thread_id": thread_id, "version": 0, "notes": []}
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            self._schema(db)
            version = self._version(db, thread_id)
            rows = db.execute(
                "SELECT note_id, body, version, created_at FROM notes WHERE thread_id=? ORDER BY version",
                (thread_id,),
            ).fetchall()
        return {
            "thread_id": thread_id,
            "version": version,
            "notes": [
                {"note_id": row[0], "body": row[1], "version": row[2], "created_at": row[3]}
                for row in rows
            ],
        }

    def receipt(self, thread_id: str, operation_id: str) -> dict[str, Any] | None:
        thread_id = self._identifier(thread_id, "thread_id")
        operation_id = self._identifier(operation_id, "operation_id")
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            self._schema(db)
            row = db.execute(
                "SELECT note_id, version, created_at FROM notes WHERE thread_id=? AND operation_id=?",
                (thread_id, operation_id),
            ).fetchone()
        return self._receipt(thread_id, operation_id, row, "committed") if row else None

    def reconcile_save(self, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Only reconcile a lost response when the committed command has the same body."""
        thread_id = self._identifier(arguments["thread_id"], "thread_id")
        operation_id = self._identifier(arguments["operation_id"], "operation_id")
        body = arguments["body"]
        if not isinstance(body, str) or not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            self._schema(db)
            row = db.execute(
                "SELECT note_id, version, created_at, body_hash, body FROM notes "
                "WHERE thread_id=? AND operation_id=?",
                (thread_id, operation_id),
            ).fetchone()
        if row is None or row[3] != hashlib.sha256(body.encode("utf-8")).hexdigest() or row[4] != body:
            return None
        return self._receipt(thread_id, operation_id, row[:3], "committed")

    def save(
        self, *, thread_id: str, operation_id: str, body: str, expected_version: int,
    ) -> dict[str, Any]:
        thread_id = self._identifier(thread_id, "thread_id")
        operation_id = self._identifier(operation_id, "operation_id")
        if not isinstance(body, str) or not body.strip() or len(body) > 5000:
            raise ValueError("note body must contain 1-5000 characters")
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version must be a nonnegative integer")
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
                existing = db.execute(
                    "SELECT note_id, version, created_at, body_hash, body FROM notes "
                    "WHERE thread_id=? AND operation_id=?",
                    (thread_id, operation_id),
                ).fetchone()
                if existing:
                    if existing[3] != content_hash or existing[4] != body:
                        raise NoteConflictError("operation_id_reused_with_different_note")
                    result = self._receipt(thread_id, operation_id, existing[:3], "replayed")
                else:
                    current = self._version(db, thread_id)
                    if expected_version != current:
                        raise NoteConflictError("stale_thread_version")
                    version = current + 1
                    row = (str(uuid.uuid4()), version, utc_now())
                    db.execute(
                        "INSERT INTO notes (thread_id, operation_id, note_id, body, body_hash, version, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (thread_id, operation_id, row[0], body, content_hash, version, row[2]),
                    )
                    db.execute(
                        "INSERT INTO threads (thread_id, version) VALUES (?, ?) "
                        "ON CONFLICT(thread_id) DO UPDATE SET version=excluded.version",
                        (thread_id, version),
                    )
                    result = self._receipt(thread_id, operation_id, row, "created")
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _schema(db: sqlite3.Connection) -> None:
        db.execute("CREATE TABLE IF NOT EXISTS threads (thread_id TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS notes ("
            "thread_id TEXT NOT NULL, operation_id TEXT NOT NULL, note_id TEXT NOT NULL, "
            "body TEXT NOT NULL, body_hash TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, "
            "PRIMARY KEY(thread_id, operation_id), UNIQUE(thread_id, version))"
        )

    @staticmethod
    def _version(db: sqlite3.Connection, thread_id: str) -> int:
        row = db.execute("SELECT version FROM threads WHERE thread_id=?", (thread_id,)).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _receipt(thread_id: str, operation_id: str, row: tuple[Any, ...], status: str) -> dict[str, Any]:
        return {
            "status": status, "thread_id": thread_id, "operation_id": operation_id,
            "note_id": row[0], "version": int(row[1]), "created_at": row[2],
        }

    @staticmethod
    def _identifier(value: str, label: str) -> str:
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError(f"invalid {label}")
        return value


def learning_note_tools(store: LearningNoteStore) -> list[RuntimeTool]:
    """Register one read and one gated write on the upstream tool runtime."""
    return [
        RuntimeTool(
            name="list_learning_notes", description="Read notes for one local learning thread.",
            action=lambda args: store.list_notes(args["thread_id"]),
            input_schema={"type": "object", "required": ["thread_id"],
                          "properties": {"thread_id": {"type": "string"}},
                          "additionalProperties": False},
            max_read_retries=1,
        ),
        RuntimeTool(
            name="save_learning_note", description="Save one explicitly confirmed learning note.",
            action=lambda args: store.save(**args),
            approval_action="write_file", risk_level="none",
            fixed_target_path=store.path,
            input_schema={"type": "object", "required": ["thread_id", "operation_id", "body", "expected_version"],
                          "properties": {"thread_id": {"type": "string"},
                                         "operation_id": {"type": "string"},
                                         "body": {"type": "string"},
                                         "expected_version": {"type": "integer"}},
                          "additionalProperties": False},
            may_write=True,
            receipt_lookup=store.reconcile_save,
            definitive_exceptions=(NoteConflictError, ValueError),
        ),
    ]


class _ExplicitCommandModel:
    """Feed an explicit local command through the same tool boundary, without an LLM."""

    def __init__(self, tool_name: str, arguments: dict[str, Any]):
        self.tool_name = tool_name
        self.arguments = arguments
        self.sent = False

    def complete(self, messages, tools) -> ToolModelResponse:
        if not self.sent:
            self.sent = True
            return ToolModelResponse(content="local command", tool_calls=[
                ToolCall(call_id="explicit-command", name=self.tool_name, arguments=self.arguments),
            ])
        return ToolModelResponse(content="local command completed")


def execute_learning_note_command(
    store: LearningNoteStore, tool_name: str, arguments: dict[str, Any], *, user_confirmed: bool = False,
) -> AgentRuntimeResult:
    """CLI adapter: confirmation comes from the explicit command, never model text."""
    runtime = AgentRuntime(
        config=AgentConfig.default(workspace_root=store.workspace_root),
        model=_ExplicitCommandModel(tool_name, arguments),
        tools=learning_note_tools(store), max_turns=2, max_tool_steps=1,
        approved_by="explicit-local-user" if user_confirmed else None,
    )
    return runtime.run("execute explicit local learning-note command")
