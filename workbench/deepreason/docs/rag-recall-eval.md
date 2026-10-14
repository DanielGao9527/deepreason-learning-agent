# RAG Recall Evaluation

Date: 2026-07-07

## Current Mechanism

The current RAG implementation is `hybrid`, implemented by `LocalKnowledgeBase` in `src/reasoning_agent_template/knowledge.py`.

- Supported files: `.md`, `.txt`, `.json`
- Index unit: paragraph/size-bounded chunks with stable line spans
- Local methods:
  - `keyword`: legacy lexical overlap
  - `bm25`: local BM25-style scorer
  - `semantic`: deterministic multilingual semantic approximation with synonym/glossary expansion
  - `graph`: local term co-occurrence graph expansion
- Fallback methods:
  - `wiki`: optional Wikipedia API fallback
- Ranking: weighted hybrid score with per-method `score_breakdown`
- `agent.yaml` sets `knowledge.index_type: hybrid`
- Active project methods: `bm25 + semantic + graph`, with `wiki` as fallback
- Debug API: `POST /api/rag/query`

## Test Data

Added 10 synthetic documents under `knowledge/rag_eval_test/`:

- `01_vector_hnsw.md`
- `02_bm25_keyword.md`
- `03_graph_rag.md`
- `04_cross_encoder_reranker.md`
- `05_chunking_overlap.md`
- `06_high_entropy_alloy_strength.md`
- `07_memory_gate_policy.md`
- `08_self_evolution_proposal.md`
- `09_state_machine_workflow.md`
- `10_secret_rotation.md`

The full index contained 13 chunks during the test: the 10 synthetic files plus the 3 existing files in `knowledge/`.

## Baseline Results Before Upgrade

| Query Set | Count | Recall@1 | Recall@3 | Recall@5 |
|---|---:|---:|---:|---:|
| Direct lexical + light paraphrase | 16 | 100.0% | 100.0% | 100.0% |
| Hard paraphrase | 8 | 62.5% | 87.5% | 87.5% |
| Chinese queries to English docs | 4 | 0.0% | 0.0% | 0.0% |
| Hard paraphrase + Chinese combined | 12 | 41.7% | 58.3% | 58.3% |

## Results After Hybrid Upgrade

Methods: `bm25 + semantic + graph`

| Query Set | Count | Recall@1 | Recall@3 | Recall@5 |
|---|---:|---:|---:|---:|
| Direct lexical | 10 | 100.0% | 100.0% | 100.0% |
| Hard paraphrase | 8 | 87.5% | 100.0% | 100.0% |
| Chinese queries to English docs | 4 | 75.0% | 100.0% | 100.0% |
| All combined | 22 | 90.9% | 100.0% | 100.0% |

## Observations

- Hybrid retrieval preserves exact-term performance.
- Hard paraphrase recall improves from `87.5% Recall@5` to `100.0% Recall@3`.
- Chinese-to-English recall improves from `0.0% Recall@5` to `100.0% Recall@3` on this controlled set.
- BM25 can over-score a single weak local document, so gate qualification now also checks semantic score when the retrieval method contains `semantic`.
- Wiki remains a fallback method rather than a default unit-test dependency.
- Live API smoke test after restart verified:
  - `methods=["bm25","semantic","graph"]` retrieves `knowledge/rag_eval_test/06_high_entropy_alloy_strength.md` for `高熵合金强度受哪些微观组织因素影响`.
  - `methods=["graph"]` returns graph-only `score_breakdown` entries.
  - `methods=["wiki"]` returns Wikipedia results with provider diagnostics after adding a User-Agent header.

## Recommended Next Step

For production deployment, the next upgrades should be:

1. Replace deterministic semantic approximation with a real embedding provider adapter.
2. Add persistent index caching and incremental reindexing.
3. Add a cross-encoder or LLM reranker for high-risk evidence workflows.
4. Add graph entity extraction beyond term co-occurrence.
5. Add benchmark datasets per target domain.
