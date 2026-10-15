"""Execution exclusion and complete-file snapshots for the local learning entrypoint."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile

from reasoning_agent_template.sessions import SessionSnapshot, SessionStore


class LearningSessionBusyError(RuntimeError):
    def __init__(self, code: str = "session_busy"):
        self.code = code
        super().__init__("当前学习助手或会话已有请求正在执行，请等待完成后再试。")


@contextmanager
def session_execution_guard(store: SessionStore, thread_id: str):
    """Hold a nonblocking OS lock from history loading through snapshot commit.

    Use the actual snapshot path as the key, including Windows case folding.
    Keep the lock file after closing: unlinking it could create two lock targets.
    """
    snapshot_path = store._snapshot_path(thread_id)
    key = hashlib.sha256(os.path.normcase(str(snapshot_path)).encode("utf-8")).hexdigest()
    directory = store.root.resolve().parent / "local_state" / "session_locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{key}.lock").open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise LearningSessionBusyError() from None
            raise
        # Closing the descriptor releases the lock, also when the body raises.
        yield


class LearningSessionStore(SessionStore):
    """Reuse the upstream transcript format; replace only the file-write boundary."""

    def _write(self, snapshot: SessionSnapshot) -> None:
        path = self._snapshot_path(snapshot.session_id)
        payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent,
                prefix=".snapshot-", suffix=".tmp", delete=False,
            ) as output:
                temporary = Path(output.name)
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
