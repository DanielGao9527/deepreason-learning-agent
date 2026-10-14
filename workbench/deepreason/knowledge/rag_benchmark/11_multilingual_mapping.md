# RAG Benchmark: Multilingual Mapping
Document id: rag_benchmark_multilingual_mapping.

Multilingual retrieval needs query expansion, domain glossary terms, and cross-language aliases. Chinese questions about 高熵合金 should map to high entropy alloy and HEA. Questions about 证据门禁 should map to evidence gate, approval, audit, and gate decision.

The deterministic semantic scorer approximates this behavior with glossary expansion and character or word n-gram features. A real embedding model is still recommended for production.

中文说明：多语言召回依赖领域词表、同义词和跨语言别名。当前实现是确定性近似，不等同于真正的嵌入模型。

当用户问“中文问题里的证据门禁应该映射到哪些英文检索词”时，推荐英文检索词包括 evidence gate, approval gate, evidence audit, gate decision, claim support, source requirement, reviewer check, and retrieval fallback.
