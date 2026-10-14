---
name: minimal-change
description: Use when planning or performing code, config, skill, documentation, or memory edits where the agent must make the smallest evidence-backed modification, avoid unrelated refactors, preserve user changes, and verify the exact requested behavior.
---

# Minimal Change

## Core Rule

Make the smallest change that satisfies the user's goal and passes verification. Prefer local edits over broad rewrites.

## Workflow

1. Inspect the current file or artifact before editing.
2. Identify the smallest ownership boundary that contains the issue.
3. List files that should change and files that must not change.
4. Preserve unrelated user work.
5. Apply the edit.
6. Verify the specific behavior that motivated the edit.

## Refactor Boundary

Refactor only when it directly reduces risk for the requested change. Do not rename symbols, reformat unrelated files, upgrade dependencies, or reorganize directories unless the acceptance criteria require it.

## Evidence Requirement

For every non-trivial edit, record the source of truth: test failure, user request, config rule, evidence item, or code reference.
