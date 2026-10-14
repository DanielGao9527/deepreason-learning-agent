# RAG Benchmark: Wiki Fallback Policy
Document id: rag_benchmark_wiki_fallback_policy.

Wikipedia fallback should be treated as a secondary evidence source. The local RAG index is queried first. If the best local score is below the fallback threshold, or if the user explicitly selects Wiki in the debug console, the runtime may call the Wikipedia API and record provider diagnostics.

Wiki results are normalized into citable chunks with URL, title, summary, score, retrieval method, and score breakdown. They should not silently replace local project documents.

中文说明：Wiki 是替补项。它不参与本地索引初始化，只在本地召回不足或用户显式勾选时调用，并且必须在 diagnostics 里展示是否调用、是否失败、返回多少结果。
