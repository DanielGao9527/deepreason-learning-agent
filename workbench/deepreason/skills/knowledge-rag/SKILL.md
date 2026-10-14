---
name: knowledge-rag
description: Use when ingesting, searching, citing, or auditing local project knowledge for a heavy-reasoning agent, especially markdown, text, JSON, and other documents that must return source path, span, hash, score, and evidence id.
---

# Knowledge RAG

## Retrieval Contract

Every retrieved chunk must include:

- Source path or URI.
- Span or locator.
- Content hash.
- Retrieval score.
- Evidence id after ledger recording.

## Workflow

1. Ingest only configured knowledge roots.
2. Preserve source paths and line spans.
3. Rank by direct relevance to the user goal.
4. Record retrieved chunks in the evidence ledger.
5. Cite evidence ids in answers, gates, memory proposals, and evolution proposals.

## Boundaries

For v1, prefer local markdown, text, and JSON. Do not silently scrape the web or connect to databases. If the configured source is missing, return no evidence and let the gate interrupt instead of hallucinating.
