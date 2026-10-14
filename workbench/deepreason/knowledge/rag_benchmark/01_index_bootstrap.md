# RAG Benchmark: Index Bootstrap
Document id: rag_benchmark_index_bootstrap.

A local RAG knowledge base is initialized by placing `.md`, `.txt`, or `.json` source documents under the configured `knowledge` directory. The runtime scans supported files, splits them into stable chunks, and attaches source path, line span, content hash, and retrieval scores.

BM25, semantic, and graph retrieval are query-time scorers over the same chunk set. Wiki is not part of the local index; it is an external fallback source.

中文说明：初始化知识库时，把资料放到 `knowledge/` 下。系统会递归扫描、分块、记录来源路径和行号，再在查询时建立 BM25、语义向量和局部共现图评分关系。
