# RAG Benchmark Report

- Knowledge directory: `knowledge`
- Sources: `25`
- Chunks: `25`
- Cases: `18`
- Min score: `0.1`

## Recall

| Method | Recall@1 | Recall@3 | Recall@5 | Misses |
|---|---:|---:|---:|---:|
| keyword | 100.0% | 100.0% | 100.0% | 0 |
| bm25 | 100.0% | 100.0% | 100.0% | 0 |
| semantic | 100.0% | 100.0% | 100.0% | 0 |
| graph | 88.9% | 100.0% | 100.0% | 0 |
| hybrid | 100.0% | 100.0% | 100.0% | 0 |

## Misses

No misses at the largest evaluated K.

## Index Initialization Notes

The local index is initialized by `LocalKnowledgeBase.ingest()`: recurse supported files, split them into size-bounded chunks, attach source path, line span and content hash, then build method-specific scoring structures at query time.

- `keyword`: exact lexical overlap over normalized terms.
- `bm25`: per-query BM25-style scoring over expanded terms.
- `semantic`: deterministic term/synonym/trigram vector similarity.
- `graph`: local term co-occurrence graph built from the current chunk set, then query expansion through neighboring terms.
- `hybrid`: weighted merge of BM25, semantic and graph scores.
- `wiki`: external fallback source, not part of the local index.

