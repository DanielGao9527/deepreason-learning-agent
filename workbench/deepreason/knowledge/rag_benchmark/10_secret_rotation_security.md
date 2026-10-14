# RAG Benchmark: Secret Rotation Security
Document id: rag_benchmark_secret_rotation_security.

Secret rotation means replacing exposed or stale API keys, tokens, and credentials with new values, then revoking the old ones. A safe agent must avoid writing provider keys into repository files and should prefer environment variables, secure local secret files, or provider secret managers.

中文说明：密钥轮换包括生成新密钥、替换配置、撤销旧密钥和验证调用链。Agent 不应把 API key 写进仓库代码或公共配置。
