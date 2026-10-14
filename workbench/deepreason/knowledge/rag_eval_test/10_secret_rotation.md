# RAG Eval: Secret Rotation

Document id: rag_eval_secret_rotation.

Provider API keys should stay out of repository files. Secret rotation replaces exposed keys, stores the new key in a secure local file or environment variable, and verifies that application configuration does not print or commit private credentials.

