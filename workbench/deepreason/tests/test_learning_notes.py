import json
import io
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from reasoning_agent_template.config import AgentConfig
from reasoning_agent_template.learning import main as learning_main
from reasoning_agent_template.learning_notes import LearningNoteStore, NoteConflictError, learning_note_tools
from reasoning_agent_template.runtime import AgentRuntime, ToolCall, ToolModelResponse


class CommandModel:
    def __init__(self, tool_name: str, arguments: dict):
        self.tool_name = tool_name
        self.arguments = arguments
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return ToolModelResponse(content="execute", tool_calls=[
                ToolCall(call_id="call-1", name=self.tool_name, arguments=self.arguments),
            ])
        return ToolModelResponse(content="done")


class LearningNoteStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_save_and_read_are_thread_scoped(self):
        store = LearningNoteStore(self.root)
        receipt = store.save(thread_id="learner-a", operation_id="save-1", body="复习哈希冲突", expected_version=0)
        self.assertEqual(receipt["status"], "created")
        self.assertEqual(receipt["version"], 1)
        self.assertEqual(store.list_notes("learner-a")["notes"][0]["body"], "复习哈希冲突")
        self.assertEqual(store.list_notes("learner-b"), {"thread_id": "learner-b", "version": 0, "notes": []})
        self.assertEqual(store.receipt("learner-b", "save-1"), None)

    def test_same_operation_replays_after_reconstruction_and_conflicting_body_is_rejected(self):
        first = LearningNoteStore(self.root)
        created = first.save(thread_id="learner", operation_id="op-1", body="一条笔记", expected_version=0)
        second = LearningNoteStore(self.root)
        replayed = second.save(thread_id="learner", operation_id="op-1", body="一条笔记", expected_version=0)
        self.assertEqual(replayed["status"], "replayed")
        self.assertEqual(replayed["note_id"], created["note_id"])
        self.assertEqual(second.list_notes("learner")["version"], 1)
        with self.assertRaisesRegex(NoteConflictError, "operation_id_reused_with_different_note"):
            second.save(thread_id="learner", operation_id="op-1", body="改过的笔记", expected_version=1)
        self.assertEqual(len(second.list_notes("learner")["notes"]), 1)

    def test_stale_version_rejects_new_operation_without_partial_write(self):
        store = LearningNoteStore(self.root)
        store.save(thread_id="learner", operation_id="op-1", body="第一条", expected_version=0)
        with self.assertRaisesRegex(NoteConflictError, "stale_thread_version"):
            store.save(thread_id="learner", operation_id="op-2", body="第二条", expected_version=0)
        self.assertEqual(store.list_notes("learner")["version"], 1)
        self.assertEqual(store.receipt("learner", "op-2"), None)

    def test_competing_writes_with_same_thread_version_commit_only_one(self):
        store = LearningNoteStore(self.root)

        def save(index):
            try:
                return store.save(thread_id="learner", operation_id=f"op-{index}",
                                  body=f"第{index}条", expected_version=0)["status"]
            except NoteConflictError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(save, (1, 2)))
        self.assertCountEqual(outcomes, ["created", "stale_thread_version"])
        self.assertEqual(store.list_notes("learner")["version"], 1)
        self.assertEqual(len(store.list_notes("learner")["notes"]), 1)

    def test_lost_response_can_be_reconciled_in_a_new_process(self):
        store = LearningNoteStore(self.root)
        created = store.save(thread_id="learner", operation_id="op-lost", body="已成功但回执丢失", expected_version=0)
        script = (
            "import json,sys; from pathlib import Path; "
            "from reasoning_agent_template.learning_notes import LearningNoteStore; "
            "s=LearningNoteStore(Path(sys.argv[1])); "
            "print(json.dumps({'receipt':s.receipt('learner','op-lost'),"
            "'retry':s.save(thread_id='learner',operation_id='op-lost',"
            "body='已成功但回执丢失',expected_version=0),"
            "'count':len(s.list_notes('learner')['notes'])},ensure_ascii=False))"
        )
        process = subprocess.run(
            [sys.executable, "-c", script, str(self.root)],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        observed = json.loads(process.stdout)
        self.assertEqual(observed["receipt"]["note_id"], created["note_id"])
        self.assertEqual(observed["retry"]["status"], "replayed")
        self.assertEqual(observed["count"], 1)

    def test_two_processes_with_same_operation_commit_one_note(self):
        script = (
            "import json,sys; from pathlib import Path; "
            "from reasoning_agent_template.learning_notes import LearningNoteStore; "
            "s=LearningNoteStore(Path(sys.argv[1])); "
            "print(json.dumps(s.save(thread_id='learner',operation_id='op-shared',"
            "body='same note',expected_version=0)))"
        )
        processes = [subprocess.Popen([sys.executable, "-c", script, str(self.root)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8") for _ in range(2)]
        receipts = []
        for process in processes:
            output, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            receipts.append(json.loads(output))
        self.assertCountEqual([receipt["status"] for receipt in receipts], ["created", "replayed"])
        self.assertEqual(receipts[0]["note_id"], receipts[1]["note_id"])
        self.assertEqual(len(LearningNoteStore(self.root).list_notes("learner")["notes"]), 1)

    def test_two_processes_with_different_operations_cannot_both_claim_one_version(self):
        script = (
            "import json,sys; from pathlib import Path; "
            "from reasoning_agent_template.learning_notes import LearningNoteStore,NoteConflictError; "
            "s=LearningNoteStore(Path(sys.argv[1])); "
            "op=sys.argv[2]\n"
            "try:\n print(json.dumps(s.save(thread_id='learner',operation_id=op,body=op,expected_version=0)))\n"
            "except NoteConflictError as exc:\n print(json.dumps({'status':'conflict','reason':str(exc)}))"
        )
        processes = [subprocess.Popen([sys.executable, "-c", script, str(self.root), f"op-{index}"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8") for index in (1, 2)]
        outcomes = []
        for process in processes:
            output, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            outcomes.append(json.loads(output))
        self.assertCountEqual([outcome["status"] for outcome in outcomes], ["created", "conflict"])
        self.assertEqual(len(LearningNoteStore(self.root).list_notes("learner")["notes"]), 1)

    def test_invalid_input_does_not_create_database(self):
        store = LearningNoteStore(self.root)
        for values in (
            {"thread_id": "../escape", "operation_id": "op", "body": "ok", "expected_version": 0},
            {"thread_id": "learner", "operation_id": "op", "body": " ", "expected_version": 0},
            {"thread_id": "learner", "operation_id": "op", "body": "ok", "expected_version": -1},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                store.save(**values)
        self.assertFalse(store.path.exists())

    def _runtime(self, store, tool_name, arguments, *, approved_by=None, tools=None):
        return AgentRuntime(
            config=AgentConfig.default(workspace_root=self.root),
            model=CommandModel(tool_name, arguments),
            tools=tools if tools is not None else learning_note_tools(store),
            approved_by=approved_by,
        )

    def test_runtime_uses_registered_read_tool_and_requires_confirmation_for_write(self):
        store = LearningNoteStore(self.root)
        read = self._runtime(store, "list_learning_notes", {"thread_id": "learner"}).run("show notes")
        self.assertEqual(read.status, "completed")
        self.assertEqual(json.loads(read.messages[-2]["content"])["version"], 0)
        arguments = {"thread_id": "learner", "operation_id": "op-1", "body": "明确保存的笔记", "expected_version": 0}
        blocked = self._runtime(store, "save_learning_note", arguments).run("save note")
        self.assertEqual(blocked.status, "interrupted")
        self.assertFalse(store.path.exists())
        allowed = self._runtime(store, "save_learning_note", arguments, approved_by="explicit-local-user").run("save note")
        self.assertEqual(allowed.status, "completed")
        self.assertEqual(json.loads(allowed.messages[-2]["content"])["status"], "created")
        self.assertEqual(store.list_notes("learner")["version"], 1)
        replayed = self._runtime(store, "save_learning_note", arguments, approved_by="explicit-local-user").run("retry note")
        self.assertEqual(json.loads(replayed.messages[-2]["content"])["status"], "replayed")
        self.assertEqual(len(store.list_notes("learner")["notes"]), 1)

    def test_runtime_rejects_bad_schema_and_outside_workspace_path(self):
        store = LearningNoteStore(self.root)
        args = {"thread_id": "learner", "operation_id": "op-1", "body": "正文", "expected_version": 0,
                "unexpected": "ignored by the action but forbidden by schema"}
        result = self._runtime(store, "save_learning_note", args, approved_by="explicit-local-user").run("save")
        self.assertEqual(result.status, "failed")
        self.assertFalse(store.path.exists())
        with tempfile.TemporaryDirectory() as other:
            external_store = LearningNoteStore(Path(other))
            outside = self._runtime(external_store, "save_learning_note", {key: value for key, value in args.items()
                                                                           if key != "unexpected"},
                                    approved_by="explicit-local-user").run("save outside")
            self.assertEqual(outside.status, "interrupted")
            self.assertEqual(outside.gate_decisions[-1].status, "deny")
            self.assertFalse(external_store.path.exists())

    def test_timed_out_write_is_uncertain_until_receipt_then_replays_once(self):
        store = LearningNoteStore(self.root)
        args = {"thread_id": "learner", "operation_id": "op-delayed", "body": "只写一次", "expected_version": 0}
        tools = learning_note_tools(store)
        write = next(tool for tool in tools if tool.name == "save_learning_note")

        def delayed_write(arguments):
            time.sleep(0.04)
            return store.save(**arguments)

        delayed = replace(write, action=delayed_write, timeout_seconds=0.001)
        first = self._runtime(store, "save_learning_note", args, approved_by="explicit-local-user",
                              tools=[delayed]).run("save with timeout")
        self.assertEqual(first.status, "uncertain")
        self.assertEqual(store.receipt("learner", "op-delayed"), None)
        time.sleep(0.07)
        receipt = LearningNoteStore(self.root).receipt("learner", "op-delayed")
        self.assertIsNotNone(receipt)
        second = self._runtime(LearningNoteStore(self.root), "save_learning_note", args,
                               approved_by="explicit-local-user").run("retry after checking receipt")
        self.assertEqual(json.loads(second.messages[-2]["content"])["status"], "replayed")
        self.assertEqual(len(store.list_notes("learner")["notes"]), 1)

    def test_write_commits_then_loses_response_and_runtime_recovers_receipt(self):
        store = LearningNoteStore(self.root)
        args = {"thread_id": "learner", "operation_id": "op-lost-response", "body": "已写入", "expected_version": 0}
        write = next(tool for tool in learning_note_tools(store) if tool.name == "save_learning_note")

        def commit_then_fail(arguments):
            store.save(**arguments)
            raise OSError("private transport detail")

        result = self._runtime(store, "save_learning_note", args, approved_by="explicit-local-user",
                               tools=[replace(write, action=commit_then_fail)]).run("save")
        self.assertEqual(result.status, "completed")
        self.assertEqual(json.loads(result.messages[-2]["content"])["note_id"],
                         store.receipt("learner", "op-lost-response")["note_id"])
        self.assertTrue(any(event["kind"] == "tool_result_reconciled" for event in result.events))
        self.assertNotIn("private transport detail", json.dumps(result.events))
        self.assertEqual(len(store.list_notes("learner")["notes"]), 1)

    def test_timeout_cannot_reconcile_a_different_body_using_the_same_operation_id(self):
        store = LearningNoteStore(self.root)
        store.save(thread_id="learner", operation_id="op-1", body="原内容", expected_version=0)
        write = next(tool for tool in learning_note_tools(store) if tool.name == "save_learning_note")
        arguments = {"thread_id": "learner", "operation_id": "op-1", "body": "不同内容", "expected_version": 0}
        result = self._runtime(store, "save_learning_note", arguments,
                               approved_by="explicit-local-user",
                               tools=[replace(write, action=lambda _: (_ for _ in ()).throw(TimeoutError()))]).run("save")
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(store.reconcile_save(arguments), None)
        self.assertEqual(len(store.list_notes("learner")["notes"]), 1)

    def test_conflicting_idempotency_key_is_definitive_failure(self):
        store = LearningNoteStore(self.root)
        store.save(thread_id="learner", operation_id="op-1", body="原内容", expected_version=0)
        args = {"thread_id": "learner", "operation_id": "op-1", "body": "篡改内容", "expected_version": 1}
        result = self._runtime(store, "save_learning_note", args,
                               approved_by="explicit-local-user").run("save")
        self.assertEqual(result.status, "failed")
        self.assertIn("operation_id_reused_with_different_note", result.answer)
        self.assertEqual(len(store.list_notes("learner")["notes"]), 1)

    def test_read_tool_retries_one_timeout_but_write_does_not_retry(self):
        store = LearningNoteStore(self.root)
        read = next(tool for tool in learning_note_tools(store) if tool.name == "list_learning_notes")
        read_calls = 0

        def fail_once(arguments):
            nonlocal read_calls
            read_calls += 1
            if read_calls == 1:
                raise TimeoutError("temporary read stall")
            return store.list_notes(arguments["thread_id"])

        read_result = self._runtime(store, "list_learning_notes", {"thread_id": "learner"},
                                    tools=[replace(read, action=fail_once)]).run("read")
        self.assertEqual(read_result.status, "completed")
        self.assertEqual(read_calls, 2)
        self.assertEqual(len([event for event in read_result.events if event["kind"] == "tool_read_retry"]), 1)
        write = next(tool for tool in learning_note_tools(store) if tool.name == "save_learning_note")
        write_calls = 0

        def timeout_write(arguments):
            nonlocal write_calls
            write_calls += 1
            raise TimeoutError("write outcome unknown")

        args = {"thread_id": "learner", "operation_id": "op-timeout", "body": "正文", "expected_version": 0}
        write_result = self._runtime(store, "save_learning_note", args,
                                     approved_by="explicit-local-user",
                                     tools=[replace(write, action=timeout_write,
                                                    max_read_retries=1)]).run("write")
        self.assertEqual(write_result.status, "uncertain")
        self.assertEqual(write_calls, 1)
        self.assertEqual(store.receipt("learner", "op-timeout"), None)

    def test_cli_note_read_write_and_receipt_need_no_model_configuration(self):
        common = ["--workspace", str(self.root), "--thread", "learner"]

        def run(*args):
            output = io.StringIO()
            with redirect_stdout(output), patch("reasoning_agent_template.learning.qwen_client_from_env",
                                                side_effect=AssertionError("must not call Qwen")):
                code = learning_main([*common, *args])
            return code, json.loads(output.getvalue())

        self.assertEqual(run("--notes"), (0, {"notes": [], "thread_id": "learner", "version": 0}))
        code, created = run("--save-note", "记住哈希冲突的定义", "--operation-id", "op-cli",
                            "--expected-version", "0")
        self.assertEqual(code, 0)
        self.assertEqual(created["status"], "created")
        self.assertEqual(run("--note-receipt", "op-cli")[1]["note_id"], created["note_id"])
        self.assertEqual(run("--save-note", "记住哈希冲突的定义", "--operation-id", "op-cli",
                             "--expected-version", "0")[1]["status"], "replayed")
        self.assertEqual(len(run("--notes")[1]["notes"]), 1)

    def test_cli_invalid_receipt_id_returns_controlled_error(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = learning_main(["--workspace", str(self.root), "--thread", "learner",
                                    "--note-receipt", "../outside"])
        self.assertEqual(result, 2)
        self.assertIn("invalid operation_id", output.getvalue())


if __name__ == "__main__":
    unittest.main()
