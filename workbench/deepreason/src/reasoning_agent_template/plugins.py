from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from reasoning_agent_template.runtime import RuntimeTool


class PluginContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    approval_action: str | None = None
    risk_level: str = "low"
    target_path_argument: str | None = None
    permissions: list[str] = field(default_factory=list)
    load_level: str = "L3"

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, manifest_load_level: str) -> "PluginToolSpec":
        name = str(data.get("name", "")).strip()
        if not name:
            raise PluginContractError("plugin tool must declare a name")
        input_schema = data.get("input_schema") or {"type": "object"}
        if not isinstance(input_schema, dict):
            raise PluginContractError(f"tool {name} input_schema must be an object")
        return cls(
            name=name,
            description=str(data.get("description", name)),
            input_schema=dict(input_schema),
            approval_action=(
                str(data["approval_action"]) if data.get("approval_action") else None
            ),
            risk_level=str(data.get("risk_level", "low")),
            target_path_argument=(
                str(data["target_path_argument"]) if data.get("target_path_argument") else None
            ),
            permissions=[str(item) for item in data.get("permissions", [])],
            load_level=str(data.get("load_level", manifest_load_level)).upper(),
        )

    def to_runtime_proxy(self, loader: "PluginLoader") -> RuntimeTool:
        return RuntimeTool(
            name=self.name,
            description=self.description,
            action=lambda args, tool_name=self.name: loader.resolve_tool(tool_name).action(args),
            approval_action=self.approval_action,
            risk_level=self.risk_level,
            input_schema=dict(self.input_schema),
            target_path_argument=self.target_path_argument,
        )


@dataclass(frozen=True)
class PluginManifest:
    name: str
    description: str
    entrypoint: str
    load_level: str
    path: Path
    capabilities: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    tools: list[PluginToolSpec] = field(default_factory=list)

    @property
    def directory(self) -> Path:
        return self.path.parent

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise PluginContractError(f"plugin manifest must be a JSON object: {path}")
        name = str(data.get("name", "")).strip()
        if not name:
            raise PluginContractError(f"plugin manifest missing name: {path}")
        entrypoint = str(data.get("entrypoint", "")).strip()
        if ":" not in entrypoint:
            raise PluginContractError(f"plugin {name} entrypoint must use module:function")
        load_level = str(data.get("load_level", "L3")).upper()
        return cls(
            name=name,
            description=str(data.get("description", "")),
            entrypoint=entrypoint,
            load_level=load_level,
            path=path,
            capabilities=[str(item) for item in data.get("capabilities", [])],
            triggers=[str(item) for item in data.get("triggers", [])],
            permissions=[str(item) for item in data.get("permissions", [])],
            tools=[
                PluginToolSpec.from_dict(item, manifest_load_level=load_level)
                for item in data.get("tools", [])
            ],
        )

    def matches(self, selector: str) -> bool:
        return (
            selector == self.name
            or selector in self.capabilities
            or selector in self.triggers
            or any(selector == tool.name for tool in self.tools)
        )


@dataclass(frozen=True)
class PluginContext:
    manifest: PluginManifest
    workspace_root: Path
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginHandle:
    manifest_name: str
    tools: dict[str, RuntimeTool] = field(default_factory=dict)
    providers: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)


class PluginLoader:
    """Manifest-first plugin loader with optional lazy tool import.

    L1 discovery reads only plugin.json files. L2 activation imports a selected
    plugin entrypoint. L3 tool proxies expose schemas early but import the real
    implementation only when the tool action is invoked.
    """

    def __init__(
        self,
        root: Path,
        *,
        workspace_root: Path | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.root = Path(root)
        self.workspace_root = Path(workspace_root) if workspace_root is not None else self.root
        self.config = dict(config or {})
        self._manifests: dict[str, PluginManifest] = {}
        self._handles: dict[str, PluginHandle] = {}
        self._tool_cache: dict[str, RuntimeTool] = {}

    def discover(self) -> dict[str, PluginManifest]:
        manifests: dict[str, PluginManifest] = {}
        tool_owners: dict[str, str] = {}
        for manifest_path in self._manifest_paths():
            manifest = PluginManifest.from_file(manifest_path)
            if manifest.name in manifests:
                raise PluginContractError(f"duplicate plugin name: {manifest.name}")
            for tool in manifest.tools:
                owner = tool_owners.get(tool.name)
                if owner is not None:
                    raise PluginContractError(
                        f"duplicate plugin tool {tool.name}: {owner} and {manifest.name}"
                    )
                tool_owners[tool.name] = manifest.name
            manifests[manifest.name] = manifest
        self._manifests = manifests
        return dict(self._manifests)

    def activate(self, selector: str) -> list[PluginHandle]:
        matches = [manifest for manifest in self._loaded_manifests().values() if manifest.matches(selector)]
        if not matches:
            raise KeyError(f"no plugin matches {selector}")
        return [self._activate_manifest(manifest) for manifest in matches]

    def tool_proxies(self, *, capability: str | None = None) -> list[RuntimeTool]:
        manifests = self._loaded_manifests().values()
        if capability is not None:
            manifests = [manifest for manifest in manifests if manifest.matches(capability)]
        specs = [tool for manifest in manifests for tool in manifest.tools]
        return [spec.to_runtime_proxy(self) for spec in specs]

    def resolve_tool(self, tool_name: str) -> RuntimeTool:
        if tool_name in self._tool_cache:
            return self._tool_cache[tool_name]
        for manifest in self._loaded_manifests().values():
            spec = next((tool for tool in manifest.tools if tool.name == tool_name), None)
            if spec is None:
                continue
            handle = self._activate_manifest(manifest)
            tool = handle.tools.get(tool_name)
            if tool is None:
                raise PluginContractError(
                    f"plugin {manifest.name} did not return declared tool {tool_name}"
                )
            self._validate_tool_contract(tool, spec, manifest)
            self._tool_cache[tool_name] = tool
            return tool
        raise KeyError(f"unknown plugin tool: {tool_name}")

    def _loaded_manifests(self) -> dict[str, PluginManifest]:
        if not self._manifests:
            return self.discover()
        return self._manifests

    def _manifest_paths(self) -> list[Path]:
        if not self.root.exists():
            return []
        paths: list[Path] = []
        root_manifest = self.root / "plugin.json"
        if root_manifest.exists():
            paths.append(root_manifest)
        paths.extend(sorted(self.root.glob("*/plugin.json")))
        paths.extend(sorted(self.root.glob("*.plugin.json")))
        return sorted(set(paths))

    def _activate_manifest(self, manifest: PluginManifest) -> PluginHandle:
        if manifest.name in self._handles:
            return self._handles[manifest.name]
        factory = self._load_entrypoint(manifest)
        context = PluginContext(
            manifest=manifest,
            workspace_root=self.workspace_root,
            config=dict(self.config),
        )
        created = factory(context)
        handle = self._coerce_handle(manifest, created)
        self._handles[manifest.name] = handle
        return handle

    def _load_entrypoint(self, manifest: PluginManifest) -> Any:
        module_name, _, object_name = manifest.entrypoint.partition(":")
        module_name = module_name.strip()
        object_name = object_name.strip()
        if not module_name or not object_name:
            raise PluginContractError(f"invalid entrypoint for plugin {manifest.name}")

        module = self._import_entrypoint_module(manifest, module_name)
        try:
            entrypoint = getattr(module, object_name)
        except AttributeError as exc:
            raise PluginContractError(
                f"plugin {manifest.name} entrypoint object not found: {object_name}"
            ) from exc
        if not callable(entrypoint):
            raise PluginContractError(f"plugin {manifest.name} entrypoint is not callable")
        return entrypoint

    def _import_entrypoint_module(self, manifest: PluginManifest, module_name: str) -> Any:
        local_module = manifest.directory / (module_name.replace(".", "/") + ".py")
        local_package = manifest.directory / module_name.replace(".", "/") / "__init__.py"
        module_path = local_module if local_module.exists() else local_package
        if module_path.exists():
            digest = sha256(str(module_path.resolve()).encode("utf-8")).hexdigest()[:16]
            isolated_name = f"_rat_plugin_{manifest.name}_{digest}"
            spec = importlib.util.spec_from_file_location(isolated_name, module_path)
            if spec is None or spec.loader is None:
                raise PluginContractError(f"cannot load plugin module: {module_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[isolated_name] = module
            spec.loader.exec_module(module)
            return module

        inserted: list[str] = []
        for path in [str(manifest.directory), str(self.root)]:
            if path not in sys.path:
                sys.path.insert(0, path)
                inserted.append(path)
        try:
            return importlib.import_module(module_name)
        finally:
            for path in inserted:
                try:
                    sys.path.remove(path)
                except ValueError:
                    pass

    def _coerce_handle(self, manifest: PluginManifest, created: Any) -> PluginHandle:
        if isinstance(created, PluginHandle):
            return created
        if isinstance(created, dict) and any(key in created for key in ("tools", "providers", "resources")):
            return PluginHandle(
                manifest_name=manifest.name,
                tools=_coerce_tools(created.get("tools", [])),
                providers=dict(created.get("providers", {})),
                resources=dict(created.get("resources", {})),
            )
        return PluginHandle(manifest_name=manifest.name, tools=_coerce_tools(created))

    def _validate_tool_contract(
        self,
        tool: RuntimeTool,
        spec: PluginToolSpec,
        manifest: PluginManifest,
    ) -> None:
        if tool.name != spec.name:
            raise PluginContractError(
                f"plugin {manifest.name} returned tool {tool.name}, expected {spec.name}"
            )
        if spec.approval_action and tool.approval_action not in {None, spec.approval_action}:
            raise PluginContractError(
                f"plugin {manifest.name} tool {tool.name} approval_action conflicts with manifest"
            )


def _coerce_tools(value: Any) -> dict[str, RuntimeTool]:
    if value is None:
        return {}
    if isinstance(value, RuntimeTool):
        return {value.name: value}
    if isinstance(value, dict):
        if all(isinstance(item, RuntimeTool) for item in value.values()):
            return {str(name): tool for name, tool in value.items()}
        raise PluginContractError("plugin tools dict values must be RuntimeTool instances")
    if isinstance(value, (list, tuple)):
        tools: dict[str, RuntimeTool] = {}
        for item in value:
            if not isinstance(item, RuntimeTool):
                raise PluginContractError("plugin tools list items must be RuntimeTool instances")
            tools[item.name] = item
        return tools
    raise PluginContractError("plugin entrypoint must return RuntimeTool, list, dict, or PluginHandle")
