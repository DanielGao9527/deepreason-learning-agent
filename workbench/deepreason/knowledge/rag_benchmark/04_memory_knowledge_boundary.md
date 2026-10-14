# RAG Benchmark: Memory And Knowledge Boundary
Document id: rag_benchmark_memory_knowledge_boundary.

The knowledge base stores source material: documents, papers, specifications, API references, benchmark data, and project notes that should be retrieved as evidence. Long-term memory stores explicit durable facts about the user, project preferences, procedures, and episodic summaries.

Knowledge base content is ingested through RAG. Long-term memory is written only through a memory gate and should not be recursively ingested as ordinary knowledge documents.

中文说明：论文、规范、API 文档、项目资料应该进入知识库；用户偏好、项目偏好、流程性经验才进入长期记忆。二者不能混在一起，否则会污染证据系统。
