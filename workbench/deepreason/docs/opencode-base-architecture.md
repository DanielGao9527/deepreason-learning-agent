# OpenCode Base Architecture

## Position

This stack uses OpenCode as the primary agent foundation. The old local Python agent template is not the new runtime target.

The goal is low development cost: reuse OpenCode's existing agent loop, primary agents, subagents, permissions, skills, commands, sessions, snapshots, CLI, server mode, and MCP support. Custom work should be limited to configuration, prompt files, skills, MCP selection, and thin adapters to upstream tools.

## Why OpenCode

OpenCode already provides the pieces that would otherwise become expensive bottom-layer work:

- Primary agents and subagents, including built-in `build`, `plan`, `general`, `explore`, and `scout`.
- Project and global rules through `AGENTS.md`, with Claude Code compatibility fallbacks.
- Reusable `SKILL.md` skills loaded on demand through the native skill tool.
- Permission controls for read, edit, bash, task, skill, web, LSP, external directories, and stuck-loop recovery.
- MCP server integration for local and remote tools.
- CLI, TUI, web/server, sessions, fork/continue, export/import, and JSON event output.

## Stack Shape

```text
User / CLI / TUI / Web
  -> OpenCode runtime
  -> AGENTS.md project rules
  -> primary agent: architect / plan / build
  -> subagents: researcher / critic / built-in explore / scout / general
  -> skills: .opencode/skills/*
  -> tools: OpenCode built-ins + selected MCP servers
  -> optional upstream executors: Codex CLI, Aider, OpenHands, Goose, LangGraph services
```

## Capability Ownership

| Requirement | Owner |
| --- | --- |
| Agent loop | OpenCode |
| Tool call and registration | OpenCode built-ins, MCP, plugins |
| Prompt/rules | `AGENTS.md`, `.opencode/agents/*.md`, `.opencode/skills/*` |
| Multi-agent | OpenCode primary agents and subagents |
| Long/short context | OpenCode sessions, compaction, summaries |
| Memory | OpenCode session history first; Mem0/Letta via MCP only if needed |
| RAG | MCP/document service first; LlamaIndex/Haystack as external service if needed |
| Workflow | OpenCode commands and agents; production scheduler can call `opencode run` |
| Goal/loop mode | OpenCode agent steps and session continuation; avoid custom loop until proven necessary |
| State machine | Use commands/agents for v1; LangGraph only as external service for complex production flows |
| Self-evolution | proposal docs + review; no automatic prompt/skill mutation |

## Current Project Files

- `opencode.json` sets the project-level OpenCode behavior.
- `AGENTS.md` tells future OpenCode sessions to stay upstream-first.
- `.opencode/agents/architect.md` is the primary architecture agent.
- `.opencode/agents/researcher.md` is the read-only upstream comparison subagent.
- `.opencode/agents/critic.md` reviews whether a proposal is still low-maintenance.
- `.opencode/skills/opencode-base/SKILL.md` captures the reusable decision rule.

## Sources

- OpenCode config, project config precedence, and schema: https://opencode.ai/docs/config/
- OpenCode agents and subagents: https://opencode.ai/docs/agents/
- OpenCode rules and AGENTS.md: https://opencode.ai/docs/rules/
- OpenCode skills: https://opencode.ai/docs/skills/
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
