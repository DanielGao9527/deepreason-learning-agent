# 第三课：角色怎样交接，意见怎样合并

更新：2026-09-25。资料来自固定上游完整源码与四条离线运行轨迹，不是千问实测。可运行复现：在项目根目录执行 `./.venv/Scripts/python.exe scripts/trace_route_decisions.py`；结果写入 `artifacts/analysis/four_route_paths.json`。脚本把完整上游放在导入路径最前面并核对实际模块位置，外部检索固定返回空列表，三次模型答复由脚本给定。

## 先抓住一条任务主线

```text
用户问题
  → Coordinator 模型：选择难度、风险、证据需求和工作流
  → Reviewer 模型：检查这条路线是否过松
  → Python 合并规则：只接受更严格的要求
  → AgentState / 工作流：检索、证据审计、Gate
  → Worker 模型：根据状态与提示生成最终文字
  → 会话和显式长期记忆写入
```

Coordinator 与 Reviewer 是两次模型调用，Worker 是第三次。工作流里的检索、审计、Gate 和路由合并主要是代码执行；界面上出现更多角色名称，不等于真的启动了那么多自治模型。

核心入口在完整上游 [multiagent.py](../../references/deepreason-full/src/reasoning_agent_template/multiagent.py)：`run` 约 105 行，Coordinator 调用约 1300 行，Reviewer 调用约 1351 行，合并函数 `_merge_reviewer_route` 约 1904 行。工作流状态转换与 Gate 在 [workflow.py](../../references/deepreason-full/src/reasoning_agent_template/workflow.py) 约 110/517 行。注意实际行号随改动会变，优先搜函数名。

## 传递的是什么

| 谁交给谁 | 关键字段 | 谁能最终决定 |
| --- | --- | --- |
| Coordinator → Reviewer | `difficulty`, `risk_level`, `evidence_mode`, `evidence_strictness`, `sources`, `workflow`, `reasons` 等 | Coordinator 先提出，Reviewer 只能提出复核意见 |
| Reviewer → 合并代码 | `review_status`, `findings`，以及需要加严的字段 | `_merge_reviewer_route` 按字段比较，决定是否采用 |
| 合并代码 → 工作流 | 最终 `routing_decision`，内含原审查结果和来源标记 | 代码生成 `AgentState`，选择工作流路径 |
| 工作流 → Worker | 证据、门禁状态、历史上下文与状态摘要 | Worker 生成文字，但原 Reviewer 此时没有再审一遍答案 |

`review_status` 里的“escalate”并不会自动让 Reviewer 的所有字段覆盖 Coordinator。代码实际比较严格度、风险等；更弱的建议被标记为 `weaker_than_coordinator`。这是一个能解释的、由程序实现的决策规则。

## 四条真实离线轨迹

四条都是 `Coordinator → Reviewer → Worker` 三次脚本模型调用；证据库为空，外部检索固定无结果。每条最终 Worker 答案故意返回固定占位文本，用来观察控制流，**不能代表答案正确**。

| 情况 | Coordinator | Reviewer | 合并后的路线 | Gate |
| --- | --- | --- | --- | --- |
| 正常 | 简单、可选证据 | approve | 保留 routine | allow |
| Reviewer 加严 | 简单、可选证据 | 要求高风险、严格证据 | 来源为 `llm+reviewer`，进入 `evidence_strict` | 无证据，interrupt |
| Reviewer 想放宽 | 高风险、严格证据 | 给出更弱设置 | 原严格路线保留，记录 `reviewer_route_ignored` | 无证据，interrupt |
| Reviewer 坏 JSON | 简单、可选证据 | 无法解析 | 记录 `not_available`，保留原 routine | allow |

最值得讨论的是最后一行：系统没有把“审查不可用”冒充为审查通过，却允许原路线继续。若 Coordinator 本来把任务判轻了，这个降级策略可能漏掉应有的证据要求。我们后续可比较“保留原路线”“按风险中断”“降级为有限回答”的完成率与错误放行，不先断言哪一个在所有任务中最好。

加严时 Gate 返回 interrupt，但脚本模型仍收到 Worker 调用并给出固定文字。原代码把门禁状态写入 Worker 的输入；最终文字没有独立的程序级逐句核验。因此“门禁阻断了工作流”与“最终交付没有未经核实的断言”是不同的验收项。这也是后置产物审查的具体切入点。

## 本课学会到什么程度

你应能用上表说明：哪个角色提出路线、谁有修改权、为什么弱化会被忽略、坏 JSON 后怎样继续，以及哪些决定由代码而非模型做。这里没有安排入门小测；讨论下一机制时直接拿其中一条轨迹改条件、看影响。

本课只验证协作路径与规则，不证明真实模型表现、资料真实性、数据隔离或个人已掌握。下一步先选一个具体失败，例如“有门禁中断但 Worker 草稿仍含确定结论”，定义可核验的最终产物审查协议，再做代码与对照。
