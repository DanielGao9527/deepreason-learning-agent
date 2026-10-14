# 最小运行闭环与测试报告

测试日期：2026-10-14。对象是 `workbench/deepreason/` 中的学习助手，不是根目录早期工具循环样例。下面区分脚本模型离线验收、真实千问烟测与上游完整回归。**本报告记录的是第十六课比较计划接入之前的闭环基线**；最新 148 项回归和比较题结果见[项目状态](PROJECT_STATUS.md)与[第十六课](lessons/LEARNING_16_REACHABILITY_AND_BOUNDED_PLAN.md)。

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

首次验收时，[`test_learning_mvp.py`](../workbench/deepreason/tests/test_learning_mvp.py) 的 **16/16** 个学习场景测试通过，约 27.9 秒；除上述终态，还检查空语料、四种交付损坏、跨进程近期会话与 thread 隔离、本地调用上限及交互模式。当时完整工作副本的一次 142 项回归有 1 项旧 Web 状态测试超出固定一秒轮询窗口；单测重跑与同日另一次完整回归均通过。这是**修订前的历史结果**，后续结果见第 5 节。

## 4. 真实千问烟测的实际结果

本次用“什么是哈希冲突？”运行真实入口。第一步 Coordinator 路由调用即失败，服务端最终返回 HTTP **403**，错误码 `AllocationQuota.FreeTierOnly`，表示当前账号免费额度已用尽且处于“仅使用免费额度”模式。没有进入后续节点，没有真实回答，也没有该 thread 的会话快照。此前本机预占计数为 **12/100**，本次结束为 **14/100**。

之所以一次提问增加两格，是**修订前** [`multiagent.py`](../workbench/deepreason/src/reasoning_agent_template/multiagent.py) 对所有 `LLMRequestError` 统一重试一次，而 [`learning.py`](../workbench/deepreason/src/reasoning_agent_template/learning.py) 在**每次发送前**先预占一格。当时未把额度类 403 判为不可重试；这两个数是请求尝试计数，**不是成功生成次数或实际计费量**。异常文本中的 `DeepSeek HTTP` 来自复用的 [`llm.py`](../workbench/deepreason/src/reasoning_agent_template/llm.py) 客户端类；调用入口是千问适配层，不能根据错误前缀推断用了 DeepSeek。没有继续重试，也没有修改账号计费设置。

修订前单次命令行入口未捕获 `LLMRequestError`，所以当时还打印了 Python traceback；交互模式已把此类错误显示为“本轮失败”。

## 5. 2026-10-14 修订后的离线复核

客户端现在把 HTTP 状态与经白名单提取的服务端错误码写入结构化异常：400、401、403 等客户端错误立即停止；408、429、5xx 通常在原有最多两次尝试的边界内重试，已观察到的 `AllocationQuota.FreeTierOnly` 即使伴随 429 也停止。路由、路线复核、最终审查和 Worker 都读取同一 `retryable` 标志。单次命令行请求现在返回简短失败信息与退出码 2，不打印 traceback 或原始服务端响应。网络超时等原有可重试异常保持原策略。此改动不改变真实千问账号或计费状态。

| 离线注入 | 实测断言 |
| --- | --- |
| 路由调用返回额度类 403 | 仅发送并预占 **1** 次，无第二次调用、无会话快照 |
| Worker 返回 403 | Worker 仅发送 **1** 次，无会话快照 |
| 路由调用先返回 503、后成功 | 该阶段尝试 **2** 次；概念题全程共预占 **4** 次，仍在两次上限内 |
| 单次命令行调用返回 403 | 退出码 **2**，显示失败原因和“本轮未生成回答”，无 traceback |

HTTP 分类还覆盖模拟的 400、401、403、408、429、503，以及 429 携带已知额度错误码的反例，并检查错误信息不包含原始响应和测试用密钥。修改后完整工作副本 **147/147 项通过**（约 78.5 秒），七类离线终态再次 **7/7 通过**，真实千问调用 **0 次**。旧 Web 异步状态测试把固定约一秒等待改成最多五秒的单调时钟截止，完整回归通过，单测额外重复 **10/10 通过**；这是测试等待边界的修订，**不能证明运行时不存在竞态**。测试后本地示例 Ledger 已恢复，与固定上游 SHA-256 相同。

本机真实请求预占计数仍为 **14/100**。由于账号额度尚不可用，本次没有再次做真实千问端到端烟测；403 修复的结论来自离线故障注入，不能宣称真实服务已恢复。

## 6. 这份报告没有证明什么

- 脚本模型的答案是固定文本，**不能证明教学正确率、证据的语义支持或真实模型稳定性**。真实烟测因外部额度失败，本轮端到端千问回答状态为**未验证**。
- `released_gate_only` 只表示程序 Gate 放行，不代表答案经过独立事实核验；严格题的 Output Reviewer 也可能误判。现有 7 题不构成答案准确率评测集。
- 没有测并发同 thread、跨进程冲突、写工具幂等、长任务恢复、Skill 候选发布／回滚或全量知识覆盖。公开简历不能据此宣称这些能力已完成。
- 本轮使用现有 `.venv`；给出了首次克隆的安装命令，但没有在全新机器上验证安装过程。

## 7. 2026-10-14 失败终态补充验证

后续在学习助手异常路径增加脱敏本地失败文件；七类离线验收仍是 **7/7**，并在坏交付行检查 `handoff_rejected/evidence_missing` 的持久文件和无会话快照。四种坏计划记录 `plan_invalid`，四种坏交付记录 `handoff_rejected`，模拟路由 403 记录 `model_unavailable`；正常概念题不产生失败文件。测试还检查提问、thread ID、模型错误正文、服务商原始错误码不进入 JSON；重建助手对象后文件仍在；写诊断文件失败时原模型异常不会被覆盖。

新增两项测试后，学习场景 **23/23**，完整工作副本 **150/150**，真实千问 **0** 次，本机预占仍 **14/100**。失败文件仅保存控制流摘要，不是完整轨迹回放，也不会自动续跑；未分类异常可能发生在会话保存之后，其 `session_saved` 明确为未知。具体字段与源码见[第十七课](lessons/LEARNING_17_FAILURE_TERMINALS.md)。

## 8. 2026-10-14 有限补查与固定初态开关对照

离线验收新增一例实际的 Top-K 截断：五份干扰片段把“满二叉树”定义挤出前四条，Retriever 只对左侧扩大一次候选（4→12），右侧仍查一次；分数下限保持 `0.08`，随后通过原交付、Gate 与发布。验收变为 **8/8**，真实千问 **0**；14 条声明边仍仅观察到 **9 条**，完整节点序列仍 **1** 种。此补查发生在 `retrieve` 内部，不等于新增工作流路径。

`scripts/eval_bounded_recovery.py` 用相同语料指纹、全新会话和同一脚本模型，对每主体预算 1 次/2 次做三组对照：两侧定义本来可见时均回答、本地读取 2→2；定义被 Top-K 挤出时止答→回答、读取 2→3、模型调用 2→3；真正缺资料时仍止答、读取 2→3、模型调用 2→2。它只证明测试夹具中的有界可达性，**不是准确率或性能提升百分比**。原始机器结果在本机 `artifacts/analysis/bounded_recovery_ablation.json`。

故障测试覆盖预算越界、空语料不做无效补查、真实语料缺一侧继续止答、检索中新增源文件、Worker 前及 Worker 运行期间修改源文件、补查超时。源变化和超时均没有保存该轮会话；后两者分别记 `precondition_changed`、`retrieval_unavailable`。学习场景 **30/30**、完整副本 **157/157**；本轮真实千问 **0**，本机预占仍 **14/100**。源指纹检查不能充当跨进程锁，检索已写 Ledger 也未回滚。

额度可用后，用一条概念题验证真实路由、复核、Worker 与来源。下一工程入口是学习场景的一读一写工具执行保障；先核对上游 Runtime 的内存去重边界，再设计持久幂等。真正的答案质量对照仍需独立标注题、固定语料与模型配置。

## 9. 2026-10-14 明确学习笔记的工具执行实验

本项目选择了一个无需千问的真实一读一写场景：查看当前 thread 的学习笔记，以及用户显式运行 `--save-note` 保存一条。复用上游 AgentRuntime 的工具名、参数 Schema、`write_file` Gate、路径限制和超时；本项目新增 SQLite 事务，把笔记、唯一操作 ID、thread 版本与回执一起提交。普通学习问答尚不自动调用这些工具。

最简单的人工验证：先运行 `run_learning.py --notes --thread note-demo` 读版本；在全新 thread 中运行 `run_learning.py --save-note "复习哈希冲突" --thread note-demo --operation-id note-001 --expected-version 0`，预期 `created/version=1`；以同一 ID、正文和版本再次运行，预期 `replayed`，列表仍只有一条。`--note-receipt note-001 --thread note-demo` 可查询持久回执。这些命令不需要 API Key，真实千问请求为 0。具体命令及风险边界见[第十九课](lessons/LEARNING_19_TOOL_EXECUTION_ASSURANCE.md)。

故障注入覆盖：无确认时 Gate 中断、额外参数和工作区外写入被拒、旧版本并发冲突、重建对象及新进程后的同 ID 重试、两个进程同 ID 只提交一条、两个进程不同 ID 同版本只有一个成功、写线程超时后回执晚到、已提交但响应丢失时核对回执、以及 ID 相同但正文不同不能误报成功。只读超时最多重试一次，写超时不自动重试；未知写结果标 `uncertain`，不能当成失败后换 ID 重做。针对性 **17/17**、完整工作副本 **174/174**，原学习工作流离线验收 **8/8**，14 条声明边仍观察到 9 条；本轮真实千问 **0**，本机预占 **14/100**。完整回归后示例 Ledger 已恢复到固定上游哈希。

这只证明本地学习笔记表的持久幂等与版本冲突，不代表上游其他写工具、MCP、会话整体或多用户账号都具备同样保障。当前 `thread_id` 是命令行输入的本地命名空间，没有认证。不会因为保存了笔记就自动写长期画像或 Skill。

## 10. 2026-10-14 教学 Skill 的候选、审批和回退

上游 `SkillRegistry` 只发现 SKILL.md 元数据，`SelfEvolutionEngine` 只写 `proposed` JSON；默认问答没有可验证的“失败反馈→新规则对照→审批→加载→撤回”链。学习场景另做一个**固定比较题教学指令**的小闭环：来源必须是同 thread 已明确保存的反馈笔记；反馈原文不直接进入系统提示，候选只从允许的模板产生。候选绑定笔记 ID/正文哈希、当前 Skill 内容哈希；批准前重算来源、内容和三例结果。没有本地显式 `--skill-approve` 及正确哈希，候选不会影响 Worker。批准后仅在比较计划完成、Gate 放行、有合格证据时加入 Worker 提示；回退需当前哈希。命令见[第二十课](lessons/LEARNING_20_MEMORY_AND_SKILL_LIFECYCLE.md)。

固定三例（正例、证据前提变化、非比较反例）的**触发判断**：未启用版 2/3，受限候选 3/3，过宽候选 2/3；过宽候选审批被拒。完整脚本学习问答还检查批准前、批准后和回退后的 Worker 实际系统提示，而不是只检查 JSON 状态。恶意修改候选内容、评测或已启用指令都会在哈希/重算检查时阻断。针对性 **11/11**、完整工作副本 **185/185**、原学习路径离线验收 **8/8**，真实千问 **0**，本机预占仍 **14/100**；示例 Ledger 已恢复到固定上游哈希。原始三例实验报告位于本机 `artifacts/analysis/learning_skill_lifecycle.json`。

这些证据只支持“小范围 Skill 触发与版本控制”，**不支持**教学答案正确率提升、自动发现高频反馈、通用 Skill 包发布或真实用户学习效果。近期会话、历史执行证据、明确笔记、上游长期记忆与公共知识的读写边界及未完成范围见第二十课。下一步需独立答案标注题和固定初态回放；真实模型额度可用时才能测前提覆盖与调用成本。
