---
name: state-gates
description: Use when an agent action needs risk assessment, approval, state-machine routing, interrupt handling, or enforcement of evidence requirements before answering, writing files, updating memory, editing skills, executing commands, or calling external systems.
---

# State Gates

## Required State Path

Use this path unless a project config overrides it explicitly:

`intake -> plan -> retrieve -> reason -> evidence_audit -> gate -> act_or_answer -> verify -> consolidate -> respond`

Each transition must leave a trace in state. Risky actions must pass a gate before execution.

## Risk Levels

- Low: answer or read-only inspection.
- Medium: project memory write, generated config, local proposal.
- High: file write, command execution, skill edit, external API call.
- Critical: destructive operation, credential handling, production mutation.

## Gate Outcomes

- `allow`: execute or answer.
- `interrupt`: pause for evidence or human approval.
- `deny`: refuse because the action violates policy.

## Enforcement

Check evidence count, approval requirement, workspace boundaries, and target action. Never convert `interrupt` into `allow` inside the same step. Resume only with explicit approval or newly collected evidence.
