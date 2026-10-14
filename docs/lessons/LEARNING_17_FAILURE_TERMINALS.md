# 第十七课：失败为什么需要自己的终态

本课只解决一个问题：学习助手在异常退出时，怎样留下**可复查、又不泄露提问和模型正文**的最小证据。它是开发路径 B 的第一小步，尚未实现自动恢复。

## 源码原状

固定上游的 `MultiAgentOrchestrator.run` 有阶段事件和运行中状态，但异常分支清掉 `_active_run` 后原样抛错。正常结束才保存会话快照。由此，坏计划、检索交付损坏、模型 403 在终端可见，却没有统一的本地失败终态。`record_failure` 是另一条由调用方主动使用的内存状态接口，不能替代异常路径的持久记录。

## 这次新增的边界

`multiagent.py` 在异常路径调用一个默认空实现的 `_record_failed_run` 钩子；学习助手在 `learning.py` 覆盖它。异常仍向外抛出，Worker 不因记录轨迹而重试。写轨迹若失败，原始业务异常仍优先返回。

文件放在 `workbench/deepreason/learning_mvp/local_state/failures/`，一次失败一个 JSON，由临时文件原子替换写入；这个目录被 Git 忽略。测试使用临时工作区。轨迹只含 `run_id`、时间、终态、固定原因码、阶段、已完成节点、事件类型，以及适用时的边 ID 或 HTTP 状态。**不保存问题、thread ID、模型提示词、回答草稿、服务端错误正文、凭据或完整事件 payload。**

| 触发 | 终态 | 关键边界 |
| --- | --- | --- |
| 三步比较计划校验失败 | `plan_invalid` | 检索前拒绝；原因码如 `missing_dependency`、`cyclic_dependencies` |
| `retrieve → reason` 交付校验失败 | `handoff_rejected` | Worker 前拒绝；记录边 ID 和受控原因码 |
| 模型请求、缺 Key 或本地请求上限失败 | `model_unavailable` | 保留模型重试策略；记录 HTTP 状态与是否可重试，不记录错误正文 |
| 其他未分类异常 | `unexpected_error` | 只留类别；会话是否已保存标为未知，不伪称无副作用 |

“比较计划缺少一侧资料”与上表的**坏计划格式**不同：它是成功走完工作流后的 `abstained_incomplete_evidence`，保存的是受限说明，不生成失败文件。空检索同样可合法交付，但在 Worker 前止答。这些状态不能全部叫“系统报错”。

## 正常与失败实验

- 正常概念题：route → reviewer → Worker，交付答案与会话快照；不产生失败文件。
- 注入四种坏比较计划：路由和 Reviewer 已调用，检索与 Worker 均未调用；终态为 `plan_invalid`，原因码与注入错误一致，没有会话快照。
- 注入四种检索交付损坏：路由和 Reviewer 已调用，Worker 未调用；终态为 `handoff_rejected`，阶段为 `retrieve`，没有会话快照。检索阶段可能已写 Evidence Ledger，因此不能称完全无副作用。
- 模拟模型 403：请求预占一次后停止，终态为 `model_unavailable`；测试断言问题、thread ID、模型错误正文和服务端私有错误码不进入 JSON。重新构造助手对象后文件仍在。若诊断写盘故障，测试确认原模型异常没有被磁盘异常覆盖。

本课的工程取舍：**失败可追踪 ≠ 失败可恢复**。目前没有 checkpoint 续跑、没有自动重规划，没有解决同 thread 并发，也没有对真实模型服务做新请求。下一步只选一个可恢复的检索缺口，约束为最多一次补救，并证明前提变化或确实无资料时继续止答。

归属：上游复用编排器、阶段事件和会话存储；异常钩子、学习助手脱敏轨迹及故障注入为本项目与 AI 协作新增。代码在 `workbench/deepreason/src/reasoning_agent_template/{multiagent,learning}.py`；验证在 `workbench/deepreason/tests/test_learning_mvp.py` 和 `scripts/verify_learning_paths.py`。本课不能写成“全链路回放”或“自动故障恢复”。
