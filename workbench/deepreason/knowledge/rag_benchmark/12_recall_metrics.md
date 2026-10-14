# RAG Benchmark: Recall Metrics
Document id: rag_benchmark_recall_metrics.

Recall@K measures whether the expected source appears within the top K retrieved chunks. Recall@1 tests first-result precision. Recall@3 and Recall@5 test whether the retriever found the right evidence candidate before a reranker or reviewer makes the final selection.

A useful RAG benchmark should include direct lexical queries, paraphrases, relationship questions, multilingual queries, and domain questions. Misses should be inspected with score breakdowns rather than only aggregate percentages.

中文说明：召回率不是只看总分，还要看 miss case、score_breakdown 和不同检索方式的差异。混合检索应该提高复杂问题的稳定性。

Recall@1、Recall@3、Recall@5 分别表示正确来源是否出现在第 1 个、前 3 个、前 5 个检索结果中。调试时应该同时检查每个 case 的排名、top sources 和 score_breakdown。
