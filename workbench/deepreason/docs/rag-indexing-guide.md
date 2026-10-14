# RAG Indexing Guide

## Current Mechanism

The current knowledge base is local-first and file-based. Put source documents under `knowledge/`; the runtime ingests supported `.md`, `.txt`, and `.json` files.

Configured in `agent.yaml`:

```yaml
knowledge:
  directory: knowledge
  index_type: hybrid
  retrieval_methods:
    - bm25
    - semantic
    - graph
  fallback_methods:
    - wiki
  top_k: 5
  min_score: 0.1
  chunk_size: 1400
  fallback_min_score: 0.35
```

## Initialization Flow

1. Add source files under `knowledge/`.
2. Start or restart the service.
3. The first RAG query creates `LocalKnowledgeBase`.
4. `LocalKnowledgeBase.ingest()` recursively scans supported files.
5. Each file is split into size-bounded chunks.
6. Every chunk receives:
   - source path
   - line span
   - text
   - stable content hash
7. Query-time retrieval builds scores over the current chunk set.

There is no persistent vector database yet. The local index is rebuilt in memory per `LocalKnowledgeBase` instance. This is acceptable for the current local debug template, but production should add persistent index caching and real embedding storage.

## Retrieval Methods

- `keyword`: exact lexical overlap over normalized terms.
- `bm25`: BM25-style scoring over expanded local terms.
- `semantic`: deterministic synonym/glossary/n-gram vector approximation.
- `graph`: local term co-occurrence graph built from chunks, then query expansion through neighboring terms.
- `hybrid`: weighted merge of BM25, semantic, and graph scores.
- `wiki`: external fallback; it is not part of local index initialization.

Recommended default:

```text
bm25 + semantic + graph
```

Use Graph alone only for debugging relationship retrieval. It can over-rank neighboring concept chunks because local co-occurrence is intentionally broad.

## Wiki Fallback

Wiki is called in two situations:

1. The user explicitly selects `wiki` in the RAG debug panel or `/api/rag/query`.
2. The workflow's local best score is below `fallback_min_score` and `fallback_methods` contains `wiki`.

Wiki returns URL, title, summary, score, retrieval method, score breakdown, and diagnostics. Provider errors should appear in diagnostics instead of failing silently.

## Building A Clean Knowledge Base

Use this structure:

```text
knowledge/
  domain_materials/
    2026-hea-review.md
    lab-notes.md
  product_docs/
    workflow-spec.md
    gate-policy.md
  api_refs/
    provider-api.md
```

Document rules:

- Put source material in `knowledge/`: papers, specs, API docs, benchmark data, project notes.
- Put user/project preferences in `memory/`, not in `knowledge/`.
- Keep one document focused on one topic.
- Add a stable title and document id near the top.
- Include original terms plus important synonyms.
- For bilingual projects, include Chinese and English aliases for domain terms.
- Do not store secrets in knowledge files.

## Evaluation

Run:

```powershell
$env:PYTHONPATH='src'
python -m reasoning_agent_template.cli --config agent.yaml --workspace . rag-eval --cases configs/rag_benchmark_cases.json --report docs/rag-benchmark-latest.md
```

Current benchmark data:

- Documents: `knowledge/rag_benchmark/`
- Cases: `configs/rag_benchmark_cases.json`
- Latest report: `docs/rag-benchmark-latest.md`

Use the web debug console at `http://127.0.0.1:8767/`, open the RAG tab, and manually switch BM25 / Semantic / Graph / Wiki to inspect score breakdowns.
