# 最小运行闭环与测试报告

测试日期：2026-10-14。对象是 `workbench/deepreason/` 中的学习助手，不是根目录早期工具循环样例。下面区分脚本模型离线验收、真实千问烟测与上游完整回归。

## 1. 现在的最小运行闭环

```text
PowerShell 输入问题
  → LearningAssistant 接收问题、读取当前 thread 的近期会话
  → Coordinator 模型给出路由，Reviewer 模型复核
  → 10 节点 Workflow：计划 → 本地资料检索 → 证据审计 → Gate 等
  → 真实 retrieve→reason 边核对来源、片段、哈希和 Evidence Ledger
  → Gate 放行且证据足够才调用 Worker 生成最终草稿
  → 严格题额外调用 Output Reviewer，随后发布策略决定交付或扣稿
  → 保存最终可交付答复到当前 thread 的会话快照，返回答案、来源和轨迹
```

入口是 [`run_learning.py`](../run_learning.py)，场景规则在 [`learning.py`](../workbench/deepreason/src/reasoning_agent_template/learning.py)，上游编排及发布顺序在 [`multiagent.py`](../workbench/deepreason/src/reasoning_agent_template/multiagent.py)。工作流定义在 [`learning.workflow.json`](../workbench/deepreason/learning_mvp/configs/workflows/learning.workflow.json)，交付核验在 [`workflow.py`](../workbench/deepreason/src/reasoning_agent_template/workflow.py)。**10 个节点不是 10 次模型调用**：本次脚本模型中，引导回答用了 3 次角色调用，严格回答用了 4 次，资料外止答只用了 2 次。Workflow 的 `reason` 节点生成状态说明；自然语言最终草稿是在工作流结束后由 Worker 产生。上游 `verify` 节点目前只记录 Gate 是否通过，不核验最终草稿。

## 2. 最简单的复现方法

在仓库根目录运行下面第一条即可，不需要 API Key，不会消费千问额度：

首次克隆且没有 `.venv` 时，先用 `py -3.12 -m venv .venv` 创建环境，再用 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` 安装依赖。

```powershell
.\.venv\Scripts\python.exe scripts\verify_learning_paths.py
```

期望看到 `passed: 7`、`total: 7`、`real_qwen_calls: 0`。脚本逐条检查结果类型、Gate、发布状态、脚本模型调用顺序及会话是否保存；坏交付还要确认 Worker 未调用、会话未保存。完整机器结果写到本机 `artifacts/validation/learning_mvp_paths.json`；该目录不提交到 Git。

想先看三条可读轨迹，可运行：

```powershell
.\.venv\Scripts\python.exe scripts\learning_mvp_demo.py
```

预期是概念题 `guided/answered`、条件题 `deep/answered`、语料外题 `guided/abstained_no_evidence`。这个演示只展示流程，不会判断真实讲解是否正确。

完整 Python 回归在 `workbench/deepreason` 目录运行：

```powershell
$env:PYTHONPATH='src'
..\..\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

真实交互入口是在仓库根目录运行 `.\.venv\Scripts\python.exe run_learning.py`，输入问题后看回答、来源、路径、门禁和调用数；`/usage` 只读本机计数，`/exit` 退出。真实请求需要本机千问环境变量及可用额度，并受 100 次本地预占上限限制。**本次真实烟测未成功**，原因和实际计数见第 4 节；先用离线命令复现上述验收更稳妥。

## 3. 实测结果与覆盖口径

离线验收脚本本次 **7/7 通过**，约 7.1 秒，实际千问请求 **0**。每一行是事先选定的一类**终态结果**，并不代表工作流图上七条不同路线：

| 案例 | 期望且实测的结果 | Gate / 发布 | 脚本模型调用 | 会话终态 |
| --- | --- | --- | --- | --- |
| 概念解释 | `guided / answered` | `allow / released_gate_only` | route、reviewer、worker | 答案已保存 |
| 条件比较 | `deep / answered` | `allow / released_model_reviewed` | 上述三次 + output_reviewer | 答案已保存 |
| 资料外问题 | `abstained_no_evidence` | `allow / released_gate_only` | route、reviewer | 受限说明已保存；Worker 未运行 |
| 比较题缺一方定义 | `abstained_incomplete_evidence` | `allow / released_gate_only` | route、reviewer | 受限说明已保存；即使有 4 个合格片段也未调用 Worker |
| 简单但高风险请求 | `blocked` | `deny / withheld` | route、reviewer | 安全说明已保存；Worker 未运行 |
| 严格题审查不通过 | `review_withheld` | `allow / withheld` | route、reviewer、worker、output_reviewer | 草稿未进入最终答复或会话 |
| 检索交付中的证据 ID 损坏 | `WorkflowContractError:evidence_missing` | Gate 与发布均未到达 | route、reviewer | Worker 未运行；无会话快照 |

**覆盖率应这样读：**在本报告定义的七类代表性终态中，已跑通 **7/7（100%）**。六个得到正常响应的案例实际上都走相同的 10 节点主链；从轨迹的相邻节点与 Spec 对照，观察到声明的 **14 条边中的 9 条（64.3%）**。未观察到 `plan→reason` 及四条检索重试／修订／循环边；学习场景把 `workflow_retry_limit` 设为 0，不能把这些边当作已验证能力。坏交付案例在完成主链前抛错。这两个数字都**不是全部可能执行路径的覆盖率**，也不是代码行覆盖率或条件分支覆盖率；本环境未安装 `coverage`，本轮未测这些百分比。

[`test_learning_mvp.py`](../workbench/deepreason/tests/test_learning_mvp.py) 的 **16/16** 个学习场景测试通过，约 27.9 秒；除上述终态，还检查空语料、四种交付损坏、跨进程近期会话与 thread 隔离、本地调用上限及交互模式。完整工作副本本次运行 **142 项，1 项失败**：上游 Web 状态测试在固定的一秒轮询内没有等到 `completed`；该单项随即重跑 **1/1 通过**。同日此前另一次完整回归为 **142/142 通过**。这是可复现的偶发时序波动，不能写成稳定通过或已修复；位置是 [`test_multiagent_web.py`](../workbench/deepreason/tests/test_multiagent_web.py)。

## 4. 真实千问烟测的实际结果

本次用“什么是哈希冲突？”运行真实入口。第一步 Coordinator 路由调用即失败，服务端最终返回 HTTP **403**，错误码 `AllocationQuota.FreeTierOnly`，表示当前账号免费额度已用尽且处于“仅使用免费额度”模式。没有进入后续节点，没有真实回答，也没有该 thread 的会话快照。此前本机预占计数为 **12/100**，本次结束为 **14/100**。

之所以一次提问增加两格，是 [`multiagent.py`](../workbench/deepreason/src/reasoning_agent_template/multiagent.py) 对所有 `LLMRequestError` 统一重试一次，而 [`learning.py`](../workbench/deepreason/src/reasoning_agent_template/learning.py) 在**每次发送前**先预占一格。当前代码没有把这种额度类 403 判为不可重试；这会浪费本地上限，但这两个数是请求尝试计数，**不是成功生成次数或实际计费量**。异常文本中的 `DeepSeek HTTP` 来自复用的 [`llm.py`](../workbench/deepreason/src/reasoning_agent_template/llm.py) 客户端类；调用入口是千问适配层，不能根据错误前缀推断用了 DeepSeek。没有继续重试，也没有修改账号计费设置。

单次命令行入口目前没有捕获 `LLMRequestError`，所以本次还打印了 Python traceback；交互模式会把此类错误显示为“本轮失败”。这属于错误交付体验的缺口，不影响上述离线验收结论。

## 5. 这份报告没有证明什么

- 脚本模型的答案是固定文本，**不能证明教学正确率、证据的语义支持或真实模型稳定性**。真实烟测因外部额度失败，本轮端到端千问回答状态为**未验证**。
- `released_gate_only` 只表示程序 Gate 放行，不代表答案经过独立事实核验；严格题的 Output Reviewer 也可能误判。现有 7 题不构成答案准确率评测集。
- 没有测并发同 thread、跨进程冲突、写工具幂等、长任务恢复、Skill 候选发布／回滚或全量知识覆盖。公开简历不能据此宣称这些能力已完成。
- 本轮使用现有 `.venv`；给出了首次克隆的安装命令，但没有在全新机器上验证安装过程。

下一步若恢复真实模型可用额度，先用一条概念题验证路由、复核、Worker 与来源；在此之前可先针对额度类 403 的不必要重试做单独修复和离线回归。真正的质量对照还需要独立标注题、固定语料与模型配置。
