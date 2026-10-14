# Quickstart

1. Edit `agent.yaml` for the agent you want to build.
2. Put local source documents in `knowledge/`.
3. Keep constraints in `skills/*/SKILL.md`.
4. Run tests with:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

5. Enable Deep Agents later by installing the optional dependencies and setting `runtime.prefer_deepagents: true`.

Use `ConfigAssistant` when a user needs help generating a new config draft, skill recommendations, or starter acceptance tests.

## CLI

Run commands directly from the checkout:

```powershell
$env:PYTHONPATH='src'
python -m reasoning_agent_template chat "What constraints does this template enforce?"
python -m reasoning_agent_template chat --json "What constraints does this template enforce?"
python -m reasoning_agent_template skills
python -m reasoning_agent_template test
python -m reasoning_agent_template web
```

After package installation, use the console script:

```powershell
reasoning-agent chat "What constraints does this template enforce?"
reasoning-agent skills
reasoning-agent test
reasoning-agent web
```

The web debug console opens a local chat interface with:

- Multi-agent runtime status for coordinator, planner, retriever, reasoner, critic, memory, and evolver.
- State-machine trace from intake through respond.
- Evidence ledger items with hashes, source URIs, locators, and confidence.
- RAG results with source spans, scores, hashes, and evidence ids.
- Gate decisions, memory policy, enabled skills, event stream, and raw JSON.

## DeepSeek Smoke Test

`agent.yaml` uses DeepSeek model entries by default. Keep the key out of source control and provide it only through the environment:

```powershell
$env:PYTHONPATH='src'
$env:DEEPSEEK_API_KEY='<your key>'
python -m reasoning_agent_template deepseek-smoke
Remove-Item Env:\DEEPSEEK_API_KEY
```
