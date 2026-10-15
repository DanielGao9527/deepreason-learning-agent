import errno
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Event
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from reasoning_agent_template.learning import LearningAssistant, interactive_session, main
from reasoning_agent_template.learning_sessions import (
    LearningSessionBusyError, LearningSessionStore, session_execution_guard,
)
from reasoning_agent_template.llm import LLMRequestError
from tests.test_learning_mvp import CORPUS, ScriptedLearningClient


QUESTIONS = [f"什么是哈希冲突？第{index}轮。" for index in (1, 2, 3)]


class BlockedWorkerClient(ScriptedLearningClient):
    def __init__(self):
        super().__init__()
        self.entered = Event()
        self.release = Event()

    def chat(self, messages, **kwargs):
        result = super().chat(messages, **kwargs)
        if self.calls[-1] == "worker":
            self.entered.set()
            if not self.release.wait(10):
                raise TimeoutError("test worker was not released")
        return result


class LearningSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(CORPUS, self.root / "knowledge")

    def tearDown(self):
        self.temporary.cleanup()

    def assistant(self, client=None):
        return LearningAssistant(self.root, client=client or ScriptedLearningClient())

    def users(self, thread="shared"):
        return [message["content"] for message in
                LearningSessionStore(self.root / "sessions").load_messages(thread)
                if message["role"] == "user"]

    def test_warm_instances_reload_committed_history_in_a_b_a_order(self):
        a, b = self.assistant(), self.assistant()
        with patch.object(a.orchestrator, "_call_coordinator_router",
                          wraps=a.orchestrator._call_coordinator_router) as route:
            for assistant, question in zip((a, b, a), QUESTIONS):
                answer = assistant.ask(question, thread_id="shared")
                self.assertEqual(answer["learning"]["decision"], "answered")
        self.assertEqual(self.users(), QUESTIONS)
        self.assertEqual([turn["user"] for turn in route.call_args.kwargs["short_term_memory"]],
                         QUESTIONS[:2])

    def test_same_instance_rejects_other_thread_without_overwriting_active_run(self):
        client = BlockedWorkerClient()
        assistant = self.assistant(client)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(assistant.ask, QUESTIONS[0], thread_id="shared")
            try:
                self.assertTrue(client.entered.wait(5))
                with self.assertRaises(LearningSessionBusyError) as raised:
                    assistant.ask(QUESTIONS[1], thread_id="another")
                self.assertEqual(raised.exception.code, "assistant_busy")
                self.assertEqual(client.calls, ["route", "reviewer", "worker"])
                self.assertEqual(assistant.orchestrator._active_run["thread_id"], "shared")
            finally:
                client.release.set()
            self.assertEqual(first.result(timeout=5)["learning"]["decision"], "answered")
        self.assertEqual(self.users(), QUESTIONS[:1])
        self.assertFalse((self.root / "sessions" / "another").exists())

    def test_other_instance_is_rejected_during_worker_then_can_resume_latest_history(self):
        client = BlockedWorkerClient()
        a, b = self.assistant(client), self.assistant()
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(a.ask, QUESTIONS[0], thread_id="shared")
            try:
                self.assertTrue(client.entered.wait(5))
                with self.assertRaises(LearningSessionBusyError) as raised:
                    b.ask(QUESTIONS[1], thread_id="shared")
                self.assertEqual(raised.exception.code, "session_busy")
                self.assertEqual(b.client.calls, [])
                self.assertFalse((self.root / "sessions" / "shared" / "snapshot.json").exists())
                self.assertFalse((self.root / "local_state" / "failures").exists())
            finally:
                client.release.set()
            first.result(timeout=5)
        b.ask(QUESTIONS[1], thread_id="shared")
        self.assertEqual(self.users(), QUESTIONS[:2])

    def test_lock_keys_follow_upstream_thread_normalization(self):
        assistant = self.assistant()
        store = assistant.orchestrator.session_store
        with session_execution_guard(store, "learner-a"):
            with self.assertRaises(LearningSessionBusyError):
                assistant.ask(QUESTIONS[0], thread_id=" learner.a ")
        self.assertEqual(assistant.client.calls, [])
        answer = assistant.ask(QUESTIONS[0], thread_id="learner.a")
        self.assertEqual(answer["thread_id"], "learner-a")
        self.assertEqual(self.users("learner-a"), QUESTIONS[:1])

    @unittest.skipUnless(os.name == "nt", "Windows snapshot paths ignore letter case")
    def test_windows_case_aliases_share_the_same_lock(self):
        assistant = self.assistant()
        with session_execution_guard(assistant.orchestrator.session_store, "LEARNER"):
            with self.assertRaises(LearningSessionBusyError):
                assistant.ask(QUESTIONS[0], thread_id="learner")
        self.assertEqual(assistant.client.calls, [])

    def test_different_threads_and_workspaces_have_separate_locks(self):
        store = LearningSessionStore(self.root / "sessions")
        other = LearningSessionStore(self.root / "other" / "sessions")
        with session_execution_guard(store, "shared"):
            with session_execution_guard(store, "different"):
                with session_execution_guard(other, "shared"):
                    pass
        # Files stay as stable lock targets, but contain no history or identifiers.
        locks = list((self.root / "local_state" / "session_locks").glob("*.lock"))
        self.assertEqual(len(locks), 2)
        self.assertTrue(all(path.read_bytes() == b"" for path in locks))

    def test_model_failure_releases_guard_for_a_subsequent_request(self):
        assistant = self.assistant()
        with patch.object(assistant.client, "chat", side_effect=LLMRequestError(
            "controlled model failure", status_code=403, retryable=False,
        )):
            with self.assertRaises(LLMRequestError):
                assistant.ask(QUESTIONS[0], thread_id="shared")
        self.assertFalse((self.root / "sessions" / "shared" / "snapshot.json").exists())
        assistant.ask(QUESTIONS[1], thread_id="shared")
        self.assertEqual(self.users(), QUESTIONS[1:2])

    def test_failed_atomic_commit_preserves_old_file_and_discards_uncommitted_cache(self):
        assistant = self.assistant()
        assistant.ask(QUESTIONS[0], thread_id="shared")
        path = self.root / "sessions" / "shared" / "snapshot.json"
        original = path.read_bytes()
        with patch("reasoning_agent_template.learning_sessions.os.replace", side_effect=OSError("disk fault")):
            with self.assertRaises(OSError):
                assistant.ask(QUESTIONS[1], thread_id="shared")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob(".snapshot-*.tmp")), [])
        self.assertNotIn("shared", assistant.orchestrator.short_term_memories)
        with patch.object(assistant.orchestrator, "_call_coordinator_router",
                          wraps=assistant.orchestrator._call_coordinator_router) as route:
            assistant.ask(QUESTIONS[2], thread_id="shared")
        self.assertEqual(self.users(), [QUESTIONS[0], QUESTIONS[2]])
        self.assertEqual([turn["user"] for turn in route.call_args.kwargs["short_term_memory"]],
                         QUESTIONS[:1])

    def test_invalid_session_stops_before_model_or_lock_file_creation(self):
        assistant = self.assistant()
        with self.assertRaises(ValueError):
            assistant.ask(QUESTIONS[0], thread_id="../outside")
        self.assertEqual(assistant.client.calls, [])
        self.assertFalse((self.root / "local_state" / "session_locks").exists())
        assistant.ask(QUESTIONS[1], thread_id="valid")
        self.assertEqual(self.users("valid"), QUESTIONS[1:2])

    def test_corrupt_snapshot_is_not_silently_replaced_with_empty_history(self):
        path = self.root / "sessions" / "shared" / "snapshot.json"
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        assistant = self.assistant()
        with self.assertRaises(json.JSONDecodeError):
            assistant.ask(QUESTIONS[0], thread_id="shared")
        self.assertEqual(assistant.client.calls, [])
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        # An operator repairs the file; the failed request did not leave a lock.
        path.write_text(json.dumps({"session_id": "shared", "messages": []}), encoding="utf-8")
        assistant.ask(QUESTIONS[1], thread_id="shared")
        self.assertEqual(self.users(), QUESTIONS[1:2])

    def child(self, script, *args):
        env = dict(os.environ)
        workbench = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = os.pathsep.join((str(workbench / "src"), str(workbench)))
        return subprocess.Popen(
            [sys.executable, "-c", script, str(self.root), *args],
            cwd=workbench, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def stop_child(self, process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

    def test_cross_process_busy_then_abnormal_exit_releases_lock_without_cleanup(self):
        marker = self.root / "worker-started"
        script = """
import sys
from pathlib import Path
from reasoning_agent_template.learning import LearningAssistant
from tests.test_learning_mvp import ScriptedLearningClient
class Client(ScriptedLearningClient):
    def chat(self, messages, **kwargs):
        result = super().chat(messages, **kwargs)
        if self.calls[-1] == 'worker':
            Path(sys.argv[2]).write_text('ready', encoding='utf-8')
            sys.stdin.read(1)
        return result
LearningAssistant(Path(sys.argv[1]), client=Client()).ask('什么是哈希冲突？', thread_id='shared')
"""
        process = self.child(script, str(marker))
        try:
            deadline = time.monotonic() + 8
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), "child did not reach Worker")
            assistant = self.assistant()
            with self.assertRaises(LearningSessionBusyError):
                assistant.ask(QUESTIONS[1], thread_id="shared")
            self.assertEqual(assistant.client.calls, [])
            process.kill()
            process.wait(timeout=5)
            self.assertFalse((self.root / "sessions" / "shared" / "snapshot.json").exists())
            assistant.ask(QUESTIONS[2], thread_id="shared")
            self.assertEqual(self.users(), QUESTIONS[2:])
        finally:
            self.stop_child(process)

    def test_warm_assistant_reloads_a_different_process_commit(self):
        assistant = self.assistant()
        assistant.ask(QUESTIONS[0], thread_id="shared")
        script = """
import sys
from pathlib import Path
from reasoning_agent_template.learning import LearningAssistant
from tests.test_learning_mvp import ScriptedLearningClient
LearningAssistant(Path(sys.argv[1]), client=ScriptedLearningClient()).ask(sys.argv[2], thread_id='shared')
"""
        process = self.child(script, QUESTIONS[1])
        try:
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
        finally:
            self.stop_child(process)
        assistant.ask(QUESTIONS[2], thread_id="shared")
        self.assertEqual(self.users(), QUESTIONS)

    def test_cli_and_interactive_busy_errors_do_not_initialize_qwen(self):
        assistant = self.assistant()
        errors, output = io.StringIO(), io.StringIO()
        with session_execution_guard(assistant.orchestrator.session_store, "shared"):
            with redirect_stderr(errors), patch(
                "reasoning_agent_template.learning.qwen_client_from_env",
                side_effect=AssertionError("busy request must not initialize Qwen"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    main(["--workspace", str(self.root), "--thread", "shared", QUESTIONS[0]])
            self.assertEqual(raised.exception.code, 2)
            self.assertNotIn("Traceback", errors.getvalue())
            with redirect_stdout(output), patch("builtins.input", side_effect=[QUESTIONS[0], "/exit"]):
                self.assertEqual(interactive_session(assistant, thread_id="shared"), 0)
        self.assertIn("已有请求正在执行", errors.getvalue())
        self.assertIn("LearningSessionBusyError", output.getvalue())
        self.assertEqual(assistant.client.calls, [])

    def test_lock_io_failure_is_not_misreported_as_contention(self):
        target = "msvcrt.locking" if os.name == "nt" else "fcntl.flock"
        with patch(target, side_effect=OSError(errno.EIO, "storage unavailable")):
            with self.assertRaises(OSError) as raised:
                with session_execution_guard(LearningSessionStore(self.root / "sessions"), "shared"):
                    self.fail("must not enter the execution body")
        self.assertNotIsInstance(raised.exception, LearningSessionBusyError)


if __name__ == "__main__":
    unittest.main()
