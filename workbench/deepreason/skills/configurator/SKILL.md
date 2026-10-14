---
name: configurator
description: Use when helping a user understand, generate, review, or revise agent.yaml, choose skills, set knowledge and memory policies, define gates, configure models, or create starter acceptance tests for a heavy-reasoning agent.
---

# Configurator

## Output Contract

Produce a project-ready `agent.yaml` draft plus a short explanation of why each major section exists.

Cover these sections:

- `identity`: name, purpose, audience, failure boundaries.
- `models`: planner, worker, critic, grader.
- `knowledge`: directory, index type, top_k, evidence threshold.
- `memory`: partitions, read-only areas, write gates.
- `gates`: approval actions, evidence minimums, workspace boundaries.
- `skills`: enabled skill packs.
- `evolution`: proposal directory and approval rules.

## Workflow

1. Infer defaults from the template.
2. Ask only for domain choices that files cannot reveal.
3. Recommend skills based on the user's agent goal.
4. Generate acceptance tests with evidence, gate, memory, and evolution checks.
5. Keep the config local-first unless the user requests hosted infrastructure.

## Safety

Never ask for secrets in plain text. Represent missing API keys as environment variable names.
