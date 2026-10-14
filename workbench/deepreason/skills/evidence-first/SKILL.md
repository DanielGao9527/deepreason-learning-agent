---
name: evidence-first
description: Use when answering questions, making recommendations, updating memory, proposing skill changes, or passing gates where claims must be grounded in citable evidence with source type, URI, locator, content hash, confidence, and usage purpose.
---

# Evidence First

## Core Rule

Bind every key claim to at least one `EvidenceItem`. If a key claim has no evidence, mark it unsupported and either retrieve more context or lower the claim.

An acceptable evidence item contains:

- `source_type`: file, user, tool, test, web, memory, or config.
- `uri`: stable source location.
- `locator`: line range, section, test name, or turn id.
- `content_hash`: SHA-256 of the source content.
- `summary`: short evidence summary.
- `confidence`: number from 0.0 to 1.0.
- `used_for`: claim, gate, memory, evolution, or verification ids.

## Workflow

1. Identify the claims that matter to the answer or action.
2. Retrieve or inspect sources before reasoning from them.
3. Record each source in the evidence ledger.
4. Cite evidence ids in final answers and proposals.
5. If evidence conflicts, report the conflict instead of smoothing it over.

## Forbidden Shortcuts

Do not treat model memory, unstated assumptions, or uncited summaries as evidence. Do not pass high-risk gates with empty evidence. Do not write long-term memory from a single weak or ambiguous source.
