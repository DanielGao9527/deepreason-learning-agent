# OpenCode Operating Guide

## Run

Start the TUI in this project:

```powershell
opencode .
```

Run a one-shot architecture request:

```powershell
opencode run --agent architect "map memory, RAG, scheduler, and self-evolution to upstream OpenCode-compatible pieces"
```

Return raw JSON events for automation:

```powershell
opencode run --agent architect --format json "review the agent stack"
```

Inspect resolved config:

```powershell
opencode debug config
```

Do not paste resolved config into docs or issues because provider credentials may appear in it.

## Workflows

Use the custom commands inside OpenCode:

- `/agent-stack <topic>` reviews or extends the OpenCode-based stack.
- `/agent-source-map <capability>` maps a capability to OpenCode-native features, MCP, upstream tools, or thin adapters.

Use subagents by mention:

```text
@researcher compare OpenCode and OpenHands for sandboxed coding tasks
@critic review whether this proposal recreates too much framework logic
```

## Add A Skill

Create:

```text
.opencode/skills/<skill-name>/SKILL.md
```

Use lowercase hyphenated names. Include `name` and `description` frontmatter. Keep the description specific so OpenCode can choose it correctly.

## Add An Agent

Create:

```text
.opencode/agents/<agent-name>.md
```

Use frontmatter for:

- `description`
- `mode`
- `temperature`
- `steps`
- `permission`

Prefer a subagent unless the user needs to interact with it directly as a primary agent.

## Add MCP

Add disabled examples to `opencode.json` first. Enable a server only when the workflow needs it:

```json
{
  "mcp": {
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": true
    }
  }
}
```

MCP tools add to context, so avoid enabling broad servers by default.

## Secrets

Keep provider keys and private base URLs out of repo files.

Use:

- OpenCode global provider config
- environment variables like `{env:OPENAI_API_KEY}`
- secure local files via `{file:~/.secrets/key-name}`

## Upgrade Rule

Before writing custom framework code, ask:

1. Is this already native OpenCode?
2. Can a project agent or skill do it?
3. Can MCP do it?
4. Can an upstream tool be called externally?

Only write glue code after those routes fail.
