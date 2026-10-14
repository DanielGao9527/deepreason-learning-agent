# RAG Benchmark: Cross Encoder Reranking
Document id: rag_benchmark_cross_encoder_reranking.

A cross-encoder reranker scores a query and candidate passage together. It is more expensive than first-stage retrieval, but it can improve precision for hard questions where lexical or embedding search returns plausible but weakly supported passages.

In this template, reranking is a recommended production upgrade after hybrid retrieval, persistent index caching, real embeddings, and stronger graph entity extraction.

中文说明：交叉编码器重排器适合在第一阶段召回后提高精度，尤其适用于高风险证据任务，但成本高于 BM25 或向量召回。
