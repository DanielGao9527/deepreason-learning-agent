import json
import tempfile
import unittest
from pathlib import Path

from reasoning_agent_template.config import AgentConfig
from reasoning_agent_template.plugins import PluginLoader
from reasoning_agent_template.runtime import (
    AgentRuntime,
    ToolCall,
    ToolModelResponse,
)


class FakeToolModel:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, tools):
        if not self.responses:
            raise AssertionError("FakeToolModel received more calls than expected")
        return self.responses.pop(0)


class PluginLoaderTests(unittest.TestCase):
    def test_discover_reads_manifest_without_importing_plugin_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = _write_plugin(root)

            loader = PluginLoader(root)
            manifests = loader.discover()

        self.assertIn("demo", manifests)
        self.assertFalse(marker.exists())
        self.assertEqual(manifests["demo"].tools[0].name, "demo_echo")

    def test_tool_proxy_exposes_schema_and_loads_implementation_on_first_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = _write_plugin(root)

            loader = PluginLoader(root)
            proxies = loader.tool_proxies()
            schema = proxies[0].to_model_schema()
            self.assertFalse(marker.exists())

            output = proxies[0].action({"text": "hello"})
            imported = marker.exists()

        self.assertEqual(schema["name"], "demo_echo")
        self.assertEqual(schema["input_schema"]["properties"]["text"]["type"], "string")
        self.assertEqual(output, "HELLO")
        self.assertTrue(imported)

    def test_activate_loads_matching_plugin_by_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = _write_plugin(root)

            loader = PluginLoader(root)
            handles = loader.activate("echo-tools")
            imported = marker.exists()

        self.assertTrue(imported)
        self.assertEqual(len(handles), 1)
        self.assertIn("demo_echo", handles[0].tools)

    def test_manifest_permissions_are_gated_before_lazy_tool_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = _write_plugin(
                root,
                tool_name="danger_shell",
                approval_action="execute_command",
                risk_level="high",
            )
            config = AgentConfig.default(workspace_root=root)
            model = FakeToolModel(
                [
                    ToolModelResponse(
                        content="I need shell access.",
                        tool_calls=[
                            ToolCall(
                                call_id="call_1",
                                name="danger_shell",
                                arguments={"command": "echo hello"},
                            )
                        ],
                    )
                ]
            )
            loader = PluginLoader(root, workspace_root=root)
            runtime = AgentRuntime(
                config=config,
                model=model,
                tools=loader.tool_proxies(),
            )

            result = runtime.run("run a command")

        self.assertEqual(result.status, "interrupted")
        self.assertEqual(result.gate_decisions[-1].status, "interrupt")
        self.assertFalse(marker.exists())


def _write_plugin(
    root: Path,
    *,
    tool_name: str = "demo_echo",
    approval_action: str | None = None,
    risk_level: str = "low",
) -> Path:
    plugin_dir = root / "demo"
    plugin_dir.mkdir()
    marker = plugin_dir / "imported.txt"
    manifest = {
        "name": "demo",
        "description": "Demo plugin.",
        "capabilities": ["echo-tools"],
        "triggers": ["echo"],
        "permissions": ["workspace_read"],
        "load_level": "L3",
        "entrypoint": "demo_plugin:create_plugin",
        "tools": [
            {
                "name": tool_name,
                "description": "Uppercase text.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "approval_action": approval_action,
                "risk_level": risk_level,
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (plugin_dir / "demo_plugin.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "from reasoning_agent_template.runtime import RuntimeTool",
                'Path(__file__).with_name("imported.txt").write_text("yes", encoding="utf-8")',
                "",
                "def create_plugin(context):",
                "    return [",
                "        RuntimeTool(",
                f'            name="{tool_name}",',
                '            description="Uppercase text.",',
                '            action=lambda args: args.get("text", "").upper(),',
                '            input_schema={"type": "object"},',
                "        )",
                "    ]",
            ]
        ),
        encoding="utf-8",
    )
    return marker


if __name__ == "__main__":
    unittest.main()
