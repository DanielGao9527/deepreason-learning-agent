---
name: testing-verification
description: Use when defining, running, or reviewing tests and acceptance checks for a heavy-reasoning agent, especially to prove evidence binding, gate enforcement, memory safety, knowledge retrieval, state transitions, and self-evolution proposals.
---

# Testing Verification

## Verification Rule

Do not claim completion without fresh verification output. Tests must prove the behavior that matters, not just implementation details.

## Required Scenarios

Cover these scenarios for every template-derived agent:

- A knowledge question returns evidence ids.
- A key claim without evidence is blocked or downgraded.
- A high-risk action interrupts without approval.
- A memory write needs evidence and gate approval.
- A self-evolution event writes a proposal, not a direct skill mutation.
- The state trace follows the configured path.

## Test Design

Prefer deterministic local tests. Use mocks only for external model or API boundaries. Store golden tasks for regression checks when a skill, gate, memory policy, or runtime adapter changes.

## Completion

Record command, exit code, and important output. If verification fails, report the failing scenario and keep the task open.
