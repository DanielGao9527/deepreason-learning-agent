---
name: project-intake
description: Use when a user starts or revises a heavy-reasoning agent project and the agent must clarify goals, audience, scope, constraints, success criteria, failure boundaries, knowledge sources, memory policy, gates, and skills before planning or implementation.
---

# Project Intake

## Intake Contract

Produce a bounded project brief before planning implementation. Do not start tool use that mutates files until the brief identifies the user's goal, audience, constraints, and success tests.

Capture these fields:

- Goal: one sentence describing what the agent must accomplish.
- Audience: who will use or maintain the agent.
- In scope: the smallest useful version.
- Out of scope: explicit exclusions for this iteration.
- Knowledge sources: local folders, files, databases, or web sources.
- Memory policy: what can be read, proposed, or written.
- Gate policy: actions that require evidence or human approval.
- Skills: which local skills should be enabled.
- Acceptance tests: concrete scenarios that prove the agent works.

## Workflow

1. Restate the user's desired agent in one sentence.
2. Identify missing information that cannot be discovered from files.
3. Resolve discoverable facts by inspecting project files first.
4. Split oversized ideas into smaller deliverables.
5. Produce a brief that can be handed to an implementation agent.

## Hard Stops

Stop and ask the user when the goal has multiple incompatible audiences, production safety requirements are unknown, or the requested agent would need credentials or external systems that are not configured.
