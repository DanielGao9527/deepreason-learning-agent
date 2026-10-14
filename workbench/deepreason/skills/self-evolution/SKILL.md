---
name: self-evolution
description: Use when the agent should learn from failures, feedback, tests, or repeated patterns by generating reviewed proposals for skill, memory, config, or workflow improvements without directly mutating protected assets.
---

# Self Evolution

## Proposal-Only Rule

Self-evolution creates proposals. It does not directly edit base skills, core config, memory policy, or gate policy.

Each proposal must include:

- Target artifact.
- Rationale.
- Suggested change.
- Evidence ids.
- Risk level.
- Verification plan.
- Human approval requirement.

## Workflow

1. Collect failure, feedback, or regression evidence.
2. Decide whether the pattern is durable enough to learn from.
3. Create a proposal under `evolution/proposals`.
4. Route proposal review through `state-gates`.
5. Apply only after approval and verification.

## Reject Cases

Do not evolve from a single ambiguous failure, unsupported user preference, model guess, or failed test whose cause is unknown. Debug first, evolve second.
