# RAG Benchmark: Workflow Handoff Contract
Document id: rag_benchmark_workflow_handoff_contract.

A workflow edge should define a handoff contract: what upstream data is delivered, which gate or reviewer checks it, and what downstream node is allowed to assume. Planner contracts describe planned work, while gate policies describe approval or evidence requirements on the transition.

For editable workflows, a node should include agent id, work description, input contract, output contract, handler kind, handler, checkpoint flag, and gate policy.

中文说明：工作流连线不只是线条，它需要交付契约、审查条件和门禁策略。节点需要定义负责 Agent、工作内容、输入输出契约、处理器、检查点和门禁。
