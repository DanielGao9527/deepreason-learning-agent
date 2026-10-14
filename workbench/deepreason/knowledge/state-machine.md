# State Machine

The default state path is intake, plan, retrieve, reason, evidence_audit, gate, act_or_answer, verify, consolidate, and respond.

The gate stage checks evidence counts, human approval requirements, and workspace boundaries before the agent answers or acts.

中文说明：默认工作流从 intake 到 respond，包含 retrieve 检索、evidence_audit 证据审计、gate 门禁、verify 验证和 consolidate 记忆沉淀候选。调试界面会展示每个节点的输入、输出、负责 Agent 和检查点。
