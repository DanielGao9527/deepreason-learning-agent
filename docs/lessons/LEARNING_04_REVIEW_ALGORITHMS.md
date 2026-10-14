# 第四课：现有判断规则与可实现的增强

更新：2026-09-25。基于固定上游源码静态核对及上一课四条脚本模型轨迹。本文讲“代码如何决定”，不是声称已实现下述增强。

## 1. 现有路线判断：模型提案 + 字段规整 + 规则兜底

Coordinator 收到用户问题、近期对话和长期记忆；提示它输出 JSON：难度、风险、证据模式、严格度、来源、工作流等。见完整上游 `multiagent.py` 的 `_routing_messages`（约 1415 行）和 `_call_coordinator_router`（约 1300 行）。这一步主要依赖模型的语义判断，没有从用户语句算出一个统一的“复杂度公式”。

`_normalize_route_decision`（约 1832 行）限定部分字段取值、补缺失字段。若整个回答解析失败，`_fallback_route_decision` 调用 `risk.py` 的 `classify_evidence_requirement`，按内置词表/规则确定证据要求与风险，再由 `_workflow_for_route` 选择 routine / evidence_soft / evidence_strict / protected_action。**注意：字段规整并不对每一种跨字段矛盾做最终一致性校验**；例如仅取值合法，不等于“高风险却可选证据”一定被拒。

可以把这一步理解成：模型写任务单，代码检查格式；完全写坏了才走规则兜底。

## 2. 现有 Reviewer：模型复核 + 单向加严

Reviewer 看原问题、Coordinator 的结构化路线和记忆，返回 approve / escalate / revise 及建议字段、理由。`_call_reviewer` 解析它；坏 JSON 会标记 `not_available`，保留 Coordinator 路线。见 `multiagent.py` 约 1351、1450 行。

真正决定采用意见的是 `_merge_reviewer_route` 与 `_reviewer_is_stricter`（约 1904、1960 行）。只要建议把证据从 optional 提升为 required、严格度提高、风险提高或难度提高，代码就逐字段取更严格值，来源合并去重，并重新计算工作流。Reviewer 想降低要求则保留原路线；**文字上写 escalate 本身不代表一定采用**。`confidence` 是模型字段，不是上述合并的放行依据。

伪代码：

```python
if reviewer_json_unreadable:
    route = coordinator_route  # 标记 not_available
elif reviewer_is_stricter(coordinator_route, reviewer):
    route = take_stricter_fields_and_recompute_workflow()
else:
    route = coordinator_route  # 弱化意见被忽略
```

## 3. 现有证据与门禁：有限检索 + 资格筛选 + 数量阈值

最终路线进入 `workflow.py` 的 `TemplateCoordinator.run`：共享 `AgentState` 在节点之间流转，最多 32 个步骤、默认 1 次重试（配置可改）。`plan` 阶段按是否 required 决定走 retrieve 还是 reason；取回本地资料和允许的外部来源后审计。检索的本地算法包括 BM25 风格、基于词和字符片段的 semantic、词共现 graph；分数加权排序。这里的 semantic 不是学习型 embedding，graph 不是实体多跳图谱。见 `knowledge.py` 的 `_retrieve_local`（约 241 行）和 `_weighted_score`（约 547 行）。

门禁先过滤合格证据：某些任务优先外部来源；若没有外部来源，需本地检索质量过线，例如默认 `local_evidence_min_score=0.45`、语义分数门槛 `0.25`。高风险默认至少 2 条合格证据，中风险 1 条；不足返回 interrupt，保护动作可能 deny。软证据策略已尝试检索但仍不足时可 allow **受限回答**。见 `workflow.py` 的 `_qualified_gate_evidence`、`_has_strong_local_rag`、`_gate`（约 575、607、517 行）和 `gates.py` 的 `GatePolicy.evaluate`（约 29 行）。

这是一套流程与数量门槛：它能判断“有没有足够符合规则的材料”，但不能证明“两条材料都支持最终报告中的每个结论”。两份重复或过期材料也不一定是独立可靠的证据。

## 4. 现有最终回答：受提示约束，之后缺少逐结论复核

`multiagent.py` 的 `run` 约 196 行调用 Worker；`_deepseek_messages`（约 1582 行）把 Gate、证据、短/长期记忆等放进输入，并要求证据不足时不能给确定结论。Worker 返回文字后，代码主要做显示清理，然后保存会话、处理显式长期记忆写入。原 Reviewer 在回答生成之前已经完成，因此没有逐条审查最终文字。

四条离线轨迹里，严格路线因无证据而 Gate=interrupt，但脚本 Worker 仍返回固定文字。这证明代码仍调用 Worker，**不证明真实模型一定违反提示**；是否守住限制要通过真实模型与产物评测验证。

## 5. 可做的两级增强

**先补路线不变量。** 把“高风险 ⇒ required+strict”等关键关系变成代码检查。Reviewer 坏 JSON 时记录不可用，并按任务风险/明确索要来源等条件选择有限回答或中断；不要把模型输出字段合法误认为策略自洽。对照原版与新规则的错误轻量放行、过度中断、额外成本。

**重点做最终产物审查。** 在 Worker 草稿之后、展示清理与对外发布/记忆写入之前插入审查，内部证据 ID 保存在独立记录里。先只做一个评审职责：让模型列出关键结论、所引用的证据 ID、原文摘录与问题类型；程序核对 ID 属于本次合格证据、摘录确实来自该来源，Gate 不通过时不能将确定结论放行。**摘录存在只是必要条件，不等于语义支持已经被证明。** 对难核验的语义矛盾可另设独立评审，但角色数量增加需要成本对照。

最小决策可以是：`publish`（关键结论可支持）、`revise`（一次定向修改并复核）、`abstain`（证据不足、矛盾未解或预算耗尽）。裁决由代码执行有界状态转换，模型提交结构化发现；法官不能凭多数票覆盖 Gate。未核实草稿可以存为执行记录，不能晋升为已确认的长期事实。

## 6. 怎样选参数和证明值得做

先准备人工可核对的小案例集，分开发与留出，覆盖正常来源、错引用、缺资料、版本冲突、相反证据、Reviewer 坏 JSON、评审超时。对比原版、路线不变量、单产物评审；若增多职责，再对比相同调用预算的简单方案。

同时报告：正确完成数、错误发布数、弃权数、调用/token/延迟和典型失败。不能只看错误率，否则全部弃权也会显得“安全”。阈值、允许修订次数和哪些风险触发审查，只在开发集调整；留出集检验。动态权重必须等各类错误有核实标签，初期不靠模型自报信心调权。

这两级增强都是候选实现路径。当前已验证的是完整上游 118 项离线测试和四条路由轨迹；上面新规则、产物审查及效果数字均未实现。
