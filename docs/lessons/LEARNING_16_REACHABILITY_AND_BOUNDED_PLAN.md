# 第十六课：声明的工作流边与真正执行的比较计划

日期：2026-10-14。对象是 `workbench/deepreason/` 的学习助手。本课只讨论当前运行的代码，不把原框架的设计文档当作已接线功能。

## 先看原来的控制流

`learning.workflow.json` 声明 10 个节点、14 条边。`workflow.py` 的 `_select_next_edge` 在 `plan` 处按 `state.evidence_mode` 选择 `retrieve` 或 `reason`；但 `learning.py` 的 `_local_learning_route` 强制本场景为 `required`，所以学习助手不会走 `plan_to_reason`。同一文件把 `workflow_retry_limit` 设为 0，`evidence_audit_to_retrieve` 和 `gate_to_retrieve` 的重试选择条件不成立；提案循环也被这项上限关掉。`verify_to_reason` 虽有声明，现有选择器没有验证失败后选择 `revise` 边的逻辑。七类离线终态实际只观察到 9/14 条相邻节点边、1 种完整节点序列。**声明存在不等于运行可达。**

原 `_plan` 只给 `state.plan` 填五条固定文字；原 `_retrieve` 直接以 `state.user_goal` 检索，`plan_steps` 主要用于展示。即使 UI 看得到“计划”，也不能据此说 Planner 驱动了执行。

## 本轮做的有限接线

仅对 `_explicit_comparison_subjects` 识别出的显式中文双主体区别题，`LearningTemplateCoordinator._plan` 生成三个有 ID 的任务：`lookup_left`、`lookup_right` 与依赖两者的 `join_evidence`。每项都声明处理器、预期产物和完成条件，最多三步。`learning_plan.py` 在检索前检查任务 ID、依赖、循环、处理器、查询和步数；坏计划抛 `LearningPlanError`，不进入 Retriever 或 Worker，也不保存本轮会话。

`LearningTemplateCoordinator._retrieve` 按拓扑顺序实际调用上游 `LocalKnowledgeBase`：先以左主体为 query，再以右主体为 query，只有片段正文包含对应主体才列为该任务候选；最后汇合去重的证据 ID。每个任务记录状态和候选数。缺少一侧时汇合任务为 `blocked_missing_subject`，学习场景在 Worker 前返回资料不足说明。原有 Evidence Ledger、`retrieve→reason` 交付核验、Gate 和严格题最终审查仍由上游/此前改动承担。本轮没有新建检索引擎，也没有增加模型 Planner 调用。

实现位置：`learning_plan.py` 定义与校验任务；`learning.py` 的 `LearningTemplateCoordinator` 执行计划，`LearningOrchestrator` 将其接入原编排器；`multiagent.py` 新增可覆盖的 Coordinator 构造钩子并在工作流结果中展示计划；`models.py` 保存本轮计划状态。固定上游 `references/deepreason-full/` 未修改。

## 正常与失败案例

- **两侧都有资料**：测试工作区额外放入一段仅用于测试的“满二叉树／完全二叉树”定义。问题“满二叉树和完全二叉树的定义有什么区别？”实测检索器依次收到 `满二叉树`、`完全二叉树`，三任务均完成，Worker 可运行。该测试资料不是正式知识库，也不证明模型答案正确。
- **只有通用二叉树资料**：正式七文档语料中的同题没有两侧定义，计划汇合为 `blocked_missing_subject`，Worker 未调用，最终是 `abstained_incomplete_evidence`。软 Gate 仍可能显示 `allow`，它允许发布**受限说明**，不代表比较答案已有依据。
- **坏计划**：注入缺失依赖、环、不可用处理器、超出三步预算，均在检索前中断；只发生此前的路由和路线复核调用，不保存该轮会话。当前没有自动修复或重规划。

离线验证：学习场景测试 **21/21**、完整工作副本 **148/148**，七类代表性终态 **7/7**；真实千问调用 **0**。新增任务发生在原 `retrieve` 节点内部，因此上述 9/14 边与一种完整节点序列的口径不变。测试证明计划确实改变了检索 query 与止答决策，不证明检索召回率或教学准确率提升。两个 query 命中同一证据片段时保留较高检索分，避免后一查询覆盖前一查询的更强候选。

识别器只覆盖少数显式中文“A 和／与 B 有什么区别”句式，且运行在工作流目标上；若路由模型把原问题改写为不含该句式的检索目标，就不会触发此计划。每侧最多读取当前 `top_k=4` 的候选，要求片段正文含完整主体词，别名和分词变体可能被误判为资料缺失。这些都应进入下一阶段的失败与对照，而不是提前声称“复杂题自动拆解”。

## 面试时怎样准确表达

可以说：“在复用的 DeepReason 状态机里，我先核对声明边和运行选择器；随后给显式双主体比较题增加三步确定性证据计划，运行前校验依赖和处理器，让 Retriever 真正消费两个主体 query，并在缺一侧资料时阻止 Worker。”不能说“通用 DAG Planner”“模型自动拆解并修复”“多跳图谱推理”或“全路径覆盖”。下一步按 `NEXT_WORKFLOW.md` 的 B 包处理可追踪失败状态与一次有预算的恢复。
