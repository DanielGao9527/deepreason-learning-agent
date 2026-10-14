# RAG Benchmark: Graph Relationships
Document id: rag_benchmark_graph_relationships.

Graph retrieval builds a local term co-occurrence graph from indexed chunks. It expands query terms through nearby terms that repeatedly appear in the same chunk windows. This helps when the query asks about relationships, handoff dependencies, loops, or causal links rather than exact keywords.

Example: a workflow edge from `gate` back to `retrieve` is a retry relationship caused by insufficient evidence. A graph retriever should surface chunks that connect gate, evidence gap, retrieve, and retry.

中文说明：Graph 方法不是知识图谱数据库，而是本地词项共现图；它适合找“节点之间为什么连接”“哪个环节回退到哪个环节”这类关系问题。
