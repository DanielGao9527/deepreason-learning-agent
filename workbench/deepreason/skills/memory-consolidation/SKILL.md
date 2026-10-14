---
name: memory-consolidation
description: Use when deciding whether short-term state, user feedback, repeated failures, decisions, preferences, or project facts should become long-term semantic, episodic, procedural, project, or user memory under gate control.
---

# Memory Consolidation

## Memory Classes

- Semantic: durable facts and concepts.
- Episodic: notable events or interactions.
- Procedural: reusable operating procedures.
- Project: decisions specific to this workspace.
- User: explicit user preferences.
- Shared: read-only unless project policy says otherwise.

## Consolidation Workflow

1. Identify candidate memories from evidence, tests, or repeated interactions.
2. Reject transient observations and one-off guesses.
3. Attach evidence ids and confidence.
4. Pass the `write_memory` gate.
5. Write only to the configured partition if allowed.

## Proposal-First Default

When uncertain, create a memory proposal rather than writing memory directly. Never write memory without evidence. Never store secrets, credentials, or private data unless the project policy explicitly permits it.
