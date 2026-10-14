# 开源 AI 应用架构建议清单

调研日期：2026-07-01  
适用范围：从个人小助手、娱乐原型、知识库问答，到正式产品、重推理 Agent、企业级 AI 平台的开源技术选型。

## 结论先行

最稳妥的路线不是一上来堆 Agent，而是按风险和复杂度逐级加组件：

| 等级 | 典型需求 | 推荐架构 |
| --- | --- | --- |
| S0 脚本助手 | 一次性总结、改写、分类、批处理 | `Python/Node SDK + LiteLLM 可选 + JSON Schema/Pydantic + 本地文件/SQLite` |
| S1 个人助手 | 本地聊天、轻量工具调用、少量文档 | `Open WebUI/AnythingLLM/LibreChat 或 Streamlit/Chainlit + Ollama/云模型 + SQLite/Chroma/pgvector` |
| S2 娱乐/原型 | Discord/Telegram Bot、互动故事、小游戏 NPC、低风险 demo | `Next.js/Vercel AI SDK 或 FastAPI + Pydantic AI/Instructor + Redis/SQLite + promptfoo 基础回归` |
| S3 知识库/问答产品 | 文档检索、企业资料问答、客服知识库 | `Haystack/LlamaIndex/RAGFlow + pgvector/Qdrant/Weaviate/Milvus + reranker + citations + Langfuse/Phoenix + Ragas` |
| S4 重推理 Agent | 多步计划、工具执行、代码/数据分析、证据链 | `LangGraph + 状态机 + MCP 工具层 + sandbox + checkpoint/memory + eval/gate + 人审` |
| S5 企业平台 | 多团队、多租户、合规、统一模型网关、自托管 | `LiteLLM Gateway + vLLM/SGLang/TGI + Kubernetes + SSO/RBAC + 审计 + Guardrails/Presidio + OTel/Langfuse/Phoenix + CI/CD eval` |

这份仓库当前的定位更接近 S4：证据优先、状态机、RAG、记忆、门禁、多 Agent 调试与自演进提案。若要向 S5 走，重点不是再加一个 Agent 框架，而是补齐统一模型网关、权限、审计、评测、部署和数据治理。

## 调研方法

使用 `github-search` 技能做了 GitHub REST 搜索，覆盖：

- `LLM agent framework`
- `RAG framework vector database`
- `LLM observability evaluation guardrails`
- `open source AI chat knowledge base`

这些 broad query 都触达 GitHub 1000 结果上限，所以结论不是“穷尽所有长尾仓库”，而是对主流、活跃、工程可落地项目的高置信选型。随后核对了项目 README/官方文档页，包括 LangGraph、LlamaIndex、Haystack、Dify、RAGFlow、Open WebUI、Flowise、vLLM、SGLang、TGI、LiteLLM、Qdrant、Milvus、Weaviate、pgvector、AutoGen、CrewAI、Pydantic AI、Semantic Kernel、Langfuse、Phoenix、promptfoo、Ragas、NeMo Guardrails、Guardrails AI、Presidio、MCP、OWASP LLM Top 10。

## 按需求类型选架构

### 1. 最简单的助手

适合：个人效率脚本、单轮问答、批量生成标题、摘要、分类、轻量数据清洗。

最小架构：

```text
CLI/Notebook/Streamlit
  -> OpenAI/Anthropic/DeepSeek/Ollama SDK
  -> JSON Schema/Pydantic 输出约束
  -> 本地文件/SQLite
  -> 日志文件
```

建议库：

| 层 | 首选 | 备选 |
| --- | --- | --- |
| 模型调用 | 官方 SDK、LiteLLM | OpenRouter/云厂商 SDK |
| 结构化输出 | Pydantic、Instructor | Outlines、JSON Schema |
| UI | Streamlit、Gradio、Chainlit | CLI、Notebook |
| 存储 | SQLite、DuckDB、本地 Markdown | Postgres |
| 验证 | promptfoo 小样本回归 | pytest golden cases |

不要急着上：多 Agent、独立向量数据库、Kubernetes、复杂记忆系统。

### 2. 娱乐项目和原型

适合：角色聊天、NPC、小游戏、Bot、创意生成、轻量语音/图像玩法。

推荐架构：

```text
Next.js / Discord Bot / Telegram Bot
  -> API route / FastAPI
  -> Pydantic AI 或 Vercel AI SDK
  -> LiteLLM 或直接云模型
  -> Redis 会话缓存 + SQLite/Postgres
  -> promptfoo 回归用例
```

建议：

- 前端/聊天壳：Next.js + Vercel AI SDK、LibreChat、Open WebUI。
- 本地模型体验：Ollama、llama.cpp、LocalAI。
- 多人/实时：Socket.IO、LiveKit Agents。
- 低代码玩法：Flowise、Dify、n8n。
- 评测底线：至少保存 20 到 50 条典型对话，防止改提示词后玩法崩掉。

娱乐项目的核心是交互流畅和成本可控，通常不需要严格事实性；但只要会调用外部工具或写文件，就要加权限确认和操作日志。

### 3. 知识库 / RAG

适合：公司资料问答、合同/论文/说明书检索、客服知识库、FAQ。

推荐架构：

```text
Web UI / Chat UI
  -> API 服务
  -> 文档摄取：crawler/connector -> parser -> chunker
  -> embedding + hybrid search
  -> reranker
  -> generator with citations
  -> eval + trace + feedback
```

选型：

| 子领域 | 首选 | 适合场景 |
| --- | --- | --- |
| 可控 RAG 框架 | Haystack | 显式 pipeline、生产可控、问答/搜索系统 |
| 数据/文档 Agent | LlamaIndex | 文档索引、多数据源、RAG agent、快速开发 |
| 完整知识库产品 | RAGFlow | 深文档解析、可视化知识库、企业自托管 |
| 低代码知识库 | Dify、Flowise | 快速给业务方做工作流和应用 |
| 个人本地知识库 | AnythingLLM、Open WebUI | 本地优先、部署快、团队小 |
| 企业搜索 | Onyx、Haystack、OpenSearch/Elasticsearch | 多连接器、权限过滤、搜索体验 |

向量库：

| 规模/约束 | 推荐 |
| --- | --- |
| 原型、数据已在 Postgres | pgvector |
| 中小规模生产、过滤和运维简单 | Qdrant |
| 大规模分布式、多租户、GPU/混合检索 | Milvus |
| 对象+向量、RAG 查询接口、云原生 | Weaviate |
| 本地/嵌入式/轻量实验 | Chroma、LanceDB |

关键清单：

- 文档解析：Docling、Unstructured、Apache Tika、MinerU、marker、PyMuPDF。
- Web/数据同步：Firecrawl、Crawl4AI、Airbyte、n8n、自写 connector。
- 检索：dense + sparse/hybrid；支持 metadata filter；保留源文档、页码、段落 hash。
- 重排：FlagEmbedding/BGE reranker、Jina reranker、本地 cross-encoder 或云 rerank。
- 生成：必须带引用；高风险问答要允许“不知道”。
- 评测：Ragas 做 RAG 指标，promptfoo 做回归和红队，Langfuse/Phoenix 做 trace。
- 权限：企业知识库要做文档级 ACL，不要只在 UI 层过滤。

### 4. 轻推理应用

适合：表单填写、结构化抽取、简单工具调用、审批辅助、客服分流、SQL 生成前置解释。

推荐架构：

```text
业务 UI
  -> API
  -> 单 Agent / typed workflow
  -> 1 到 3 个工具
  -> schema validation
  -> retry + fallback
  -> trace + eval
```

建议库：

| 层 | 推荐 |
| --- | --- |
| 类型安全 Agent | Pydantic AI |
| 结构化输出 | Instructor、Pydantic、Outlines |
| JS/TS AI UI | Vercel AI SDK、Mastra、VoltAgent |
| Java/Spring | Spring AI、Semantic Kernel |
| 模型路由 | LiteLLM |
| 评测 | promptfoo、DeepEval、Ragas 按需 |

轻推理不要把每一步都交给 LLM。能用规则、SQL、正则、枚举、状态机解决的地方，先用确定性逻辑。LLM 负责理解、转换、解释和少量模糊判断。

### 5. 重推理 Agent

适合：复杂研究、代码修改、数据分析、长任务、多工具、多轮证据审计。

推荐架构：

```text
任务入口
  -> intake/risk classify
  -> planner
  -> state graph
  -> retriever/evidence
  -> tool executor with sandbox
  -> critic/verifier
  -> gate/human approval
  -> memory consolidation
  -> final answer with evidence
```

建议库：

| 子系统 | 推荐 |
| --- | --- |
| 状态图/长任务 Agent | LangGraph |
| 高层 Agent 快速封装 | Deep Agents、Pydantic AI |
| 多 Agent 协作 | CrewAI、LangGraph subgraphs、AutoGen 旧项目维护 |
| .NET/Java/Python 企业 Agent | Microsoft Agent Framework / Semantic Kernel 路线 |
| 工具协议 | MCP SDK/servers |
| 记忆 | Postgres/Redis + Mem0/Letta 按需 |
| 沙箱 | Docker、gVisor、Firecracker/微 VM、受限文件系统 |
| 工作流耐久性 | Temporal、Celery/RQ、Prefect/Dagster |

重推理项目必须加的工程约束：

- 状态可恢复：每一步有 checkpoint，不靠单次长上下文硬撑。
- 工具有权限：读、写、网络、执行命令分级审批。
- 证据可追溯：RAG 片段、网页、文件、命令输出都记录 source/hash/locator。
- 评估可重复：每个关键能力有 golden tasks。
- 人审可插入：高风险动作在执行前 gate。
- 失败可解释：保留 plan、tool trace、critic notes、final evidence。

### 6. 问答类产品

问答不等于 RAG。建议分成四类：

| 类型 | 架构重点 | 推荐 |
| --- | --- | --- |
| FAQ/客服 | 快、稳定、可运营 | Dify/RAGFlow/Open WebUI + pgvector/Qdrant + 人工反馈 |
| 企业搜索 | 权限、连接器、排序 | Haystack/Onyx + OpenSearch/Elasticsearch + vector DB |
| 专业问答 | 引用、拒答、审计 | Haystack/LlamaIndex + reranker + Ragas + guardrails |
| 数据问答/Text-to-SQL | schema 权限、SQL 审计 | DB-GPT/WrenAI + SQL validator + read-only DB replica |

问答类上线标准：

- Top-k 命中文档可解释。
- 答案引用能点回原文。
- 无引用或低置信时拒答。
- 每次回答保存 query、retrieval、prompt、model、latency、cost、feedback。
- 对 prompt injection、越权文档、敏感信息泄露做红队测试。

### 7. 正式产品

适合：有真实用户、付费、SLA、可持续迭代的 AI 功能。

推荐架构：

```text
Web/Mobile
  -> API Gateway
  -> Auth/RBAC
  -> App Service
  -> LiteLLM/Model Gateway
  -> Agent/RAG service
  -> Postgres + Redis + Object Storage + Vector DB
  -> Queue/Worker
  -> Observability + Eval CI
  -> Guardrails + audit log
```

正式产品建议默认组件：

| 层 | 推荐 |
| --- | --- |
| 前端 | Next.js/React、Vercel AI SDK、shadcn/ui |
| 后端 | FastAPI、NestJS、Spring Boot |
| 主库 | Postgres |
| 缓存/队列 | Redis/Valkey、Celery/RQ、BullMQ |
| 文件 | S3/MinIO |
| 向量 | pgvector/Qdrant 起步；Milvus/Weaviate 扩展 |
| 模型网关 | LiteLLM |
| 编排 | Pydantic AI/LangGraph/Haystack/LlamaIndex |
| 观测 | Langfuse 或 Phoenix；Prometheus/Grafana |
| 评测 | promptfoo + Ragas/DeepEval |
| 安全 | Presidio、Guardrails AI/NeMo Guardrails、OWASP LLM Top 10 checklist |

### 8. 企业项目

企业架构的核心不是“更聪明”，而是“可控、可审、可替换、可隔离”。

推荐架构：

```text
SSO/OIDC/SAML
  -> API Gateway / WAF
  -> AI Gateway: LiteLLM
  -> Policy: RBAC/ABAC/OPA
  -> App/Agent Services
  -> Private model serving: vLLM/SGLang/TGI
  -> Data plane: Postgres + Object Store + Vector DB + Search
  -> Workflow: Temporal/Airflow/Dagster
  -> Observability: OTel + Langfuse/Phoenix + Prometheus/Grafana
  -> Security: PII redaction + guardrails + audit + red-team CI
```

企业必备清单：

- 身份：SSO、SCIM、RBAC/ABAC、服务账号、短期凭证。
- 数据：租户隔离、文档 ACL、加密、保留周期、删除链路。
- 模型：模型白名单、成本预算、限流、fallback、私有模型 serving。
- 工具：MCP server 白名单、工具权限、网络出站控制、sandbox。
- 评测：上线前 eval gate、红队、回归集、漂移监控。
- 审计：每次 LLM 调用、检索、工具执行、人工审批都可追踪。
- 合规：PII/PHI/机密信息检测，供应链 SBOM，许可证扫描。
- 运维：Kubernetes、Helm/Terraform、蓝绿/金丝雀、备份恢复、容量压测。

## 按组件分层选型

### 应用壳和低代码

| 项目 | 用途 | 建议 |
| --- | --- | --- |
| Open WebUI | 自托管聊天、RAG、模型/工具接入 | 个人/团队最快落地，企业版能力需审许可证 |
| AnythingLLM | 本地优先知识库和 Agent 体验 | 个人、团队内网、PoC |
| LibreChat | ChatGPT 风格多模型聊天 | 需要成熟聊天 UI 时 |
| Dify | 低代码 Agent/workflow/RAG 平台 | 业务流程快搭，注意许可证和二开边界 |
| RAGFlow | 深文档理解知识库/RAG 产品 | 文档复杂、需要完整知识库后台 |
| Flowise | 可视化构建 Agent/RAG | 原型、流程演示、非核心生产链路 |
| n8n | 自动化和连接器 | 把 AI 接入业务系统、消息通知、审批流 |

### 编排和 Agent

| 项目 | 强项 | 注意 |
| --- | --- | --- |
| LangGraph | 长任务、状态图、可恢复 Agent | 最适合重推理核心 |
| Haystack | 显式 pipeline、RAG/QA/搜索生产化 | 工程可控性强 |
| LlamaIndex | 数据连接、索引、文档 Agent | 快速搭 RAG/文档应用 |
| Pydantic AI | 类型安全、Python 生产应用 | 轻/中度 Agent 很舒服 |
| CrewAI | 角色型多 Agent 协作 | 适合任务编排和 demo，生产要加强观测与权限 |
| AutoGen | 多 Agent 先驱框架 | 已进入维护模式，新项目谨慎 |
| Semantic Kernel / Microsoft Agent Framework | .NET/Java/Python 企业 Agent | 微软栈和企业长维支持优先 |
| DSPy | prompt/program 优化 | 适合可评测任务优化，不是通用 app 框架 |

### 模型调用、网关和推理服务

| 层 | 推荐 | 说明 |
| --- | --- | --- |
| 统一 API | LiteLLM | OpenAI 格式统一 100+ provider，支持预算、限流、日志、guardrails |
| 本地运行 | Ollama、llama.cpp、LocalAI | 个人/边缘设备/隐私 PoC |
| GPU 服务 | vLLM | 高吞吐 OpenAI-compatible serving，生产首选之一 |
| 高性能/多模态 serving | SGLang | 低延迟、高吞吐、大规模 GPU 场景 |
| Hugging Face 生态 | Text Generation Inference | HF 模型部署、Docker/K8s 友好 |
| Serving 平台 | BentoML、KServe、Ray Serve | 多模型/推理服务工程化 |

### 知识、检索和数据

| 层 | 推荐 |
| --- | --- |
| 解析 | Docling、Unstructured、Apache Tika、MinerU、marker |
| Embedding | sentence-transformers、FlagEmbedding、Jina embeddings、云 embedding |
| 向量库 | pgvector、Qdrant、Milvus、Weaviate、Chroma、LanceDB |
| 搜索 | OpenSearch、Elasticsearch、Meilisearch、Typesense |
| 对象存储 | MinIO/S3 |
| 主数据库 | Postgres |
| 缓存 | Redis/Valkey |
| 数据同步 | Airbyte、n8n、Kafka/Redpanda、Debezium |

### 评测、观测和反馈

| 项目 | 用途 |
| --- | --- |
| Langfuse | trace、prompt 管理、数据集、eval、self-host |
| Phoenix | OpenTelemetry tracing、实验、eval、debug |
| promptfoo | prompt/RAG/Agent 回归、红队、CI/CD |
| Ragas | RAG 指标、测试集生成、评估流程 |
| DeepEval | LLM 应用测试和指标 |
| MLflow/Opik | LLMOps、实验、监控、评估 |
| OpenTelemetry + Prometheus/Grafana | 通用服务观测 |

### 安全、合规和治理

| 风险 | 推荐措施 |
| --- | --- |
| Prompt injection | promptfoo red team、NeMo Guardrails、工具白名单、上下文隔离 |
| 敏感信息泄露 | Presidio、DLP、输出过滤、日志脱敏 |
| 过度代理权 | 工具权限分级、人审 gate、最小权限 token |
| 向量/embedding 弱点 | 文档 ACL、索引隔离、poisoning 检测、检索结果审计 |
| 输出不当 | Guardrails AI、NeMo Guardrails、schema validation |
| 成本失控 | LiteLLM budget、rate limit、缓存、max token 策略 |
| 供应链 | SBOM、许可证审计、镜像扫描、依赖 pin |

## 推荐组合模板

### A. 1 天内能跑的个人知识库

```text
Open WebUI 或 AnythingLLM
  + Ollama/云模型
  + 内置 RAG 或 Chroma/pgvector
  + 本地文件夹同步
```

适合验证想法，不适合直接承载权限复杂的企业资料。

### B. 可上线的知识库问答

```text
Next.js/React
  -> FastAPI
  -> Haystack 或 LlamaIndex
  -> parser/chunker
  -> pgvector/Qdrant
  -> reranker
  -> LiteLLM
  -> Langfuse/Phoenix + Ragas
```

### C. 复杂文档企业知识库

```text
RAGFlow
  -> 企业 SSO/RBAC 外挂或平台集成
  -> 私有对象存储
  -> Milvus/Elasticsearch/Postgres
  -> Langfuse/Phoenix
  -> promptfoo red team
```

### D. 轻推理业务助手

```text
业务系统
  -> FastAPI/NestJS
  -> Pydantic AI
  -> LiteLLM
  -> 业务 API 工具
  -> schema validation
  -> promptfoo golden tests
```

### E. 重推理研究/开发 Agent

```text
Chat/API/CLI
  -> LangGraph
  -> planner/retriever/reasoner/critic/verifier nodes
  -> MCP tools
  -> Docker/gVisor sandbox
  -> evidence ledger
  -> memory partitions
  -> gate policy
  -> Langfuse/Phoenix traces
```

### F. 企业 AI 平台

```text
Enterprise Portal
  -> SSO/OIDC + API Gateway
  -> LiteLLM model gateway
  -> Agent/RAG services
  -> vLLM/SGLang/TGI private serving
  -> Postgres + MinIO + Qdrant/Milvus + OpenSearch
  -> Temporal/Kafka workers
  -> OTel + Langfuse/Phoenix + Prometheus/Grafana
  -> Presidio + Guardrails + promptfoo CI
```

## 选型决策规则

1. 能用单 Agent 不用多 Agent；能用状态机不用自由对话。
2. 原型先用 pgvector/Chroma；生产再按规模换 Qdrant/Milvus/Weaviate。
3. 知识库先解决解析和权限，再谈 Agent。
4. 重推理优先 LangGraph 这类显式状态图，而不是黑箱循环。
5. 所有正式项目默认接入 trace、eval、prompt 版本管理。
6. 企业项目默认所有工具调用要可审计、可拒绝、可回放。
7. 许可证要提前审：Dify、Open WebUI、Phoenix 等项目并非都等同宽松 MIT/Apache。
8. AutoGen/Semantic Kernel 新项目要关注 Microsoft Agent Framework 迁移路径。

## 来源索引

- LangGraph: https://github.com/langchain-ai/langgraph
- LlamaIndex: https://github.com/run-llama/llama_index
- Haystack: https://github.com/deepset-ai/haystack
- Dify: https://github.com/langgenius/dify
- RAGFlow: https://github.com/infiniflow/ragflow
- Open WebUI: https://github.com/open-webui/open-webui
- AnythingLLM: https://github.com/Mintplex-Labs/anything-llm
- Flowise: https://github.com/FlowiseAI/Flowise
- vLLM: https://github.com/vllm-project/vllm
- SGLang: https://github.com/sgl-project/sglang
- Hugging Face TGI: https://github.com/huggingface/text-generation-inference
- LiteLLM: https://github.com/BerriAI/litellm
- Qdrant: https://github.com/qdrant/qdrant
- Milvus: https://github.com/milvus-io/milvus
- Weaviate: https://github.com/weaviate/weaviate
- pgvector: https://github.com/pgvector/pgvector
- AutoGen: https://github.com/microsoft/autogen
- CrewAI: https://github.com/crewAIInc/crewAI
- Pydantic AI: https://github.com/pydantic/pydantic-ai
- Semantic Kernel: https://github.com/microsoft/semantic-kernel
- Langfuse: https://github.com/langfuse/langfuse
- Phoenix: https://github.com/Arize-ai/phoenix
- promptfoo: https://github.com/promptfoo/promptfoo
- Ragas: https://github.com/explodinggradients/ragas
- NeMo Guardrails: https://github.com/NVIDIA-NeMo/Guardrails
- Guardrails AI: https://github.com/guardrails-ai/guardrails
- Presidio: https://github.com/microsoft/presidio
- Model Context Protocol: https://github.com/modelcontextprotocol
- OWASP LLM Top 10: https://genai.owasp.org/llm-top-10/
