# 第十五课：简单题也可能高风险；审查在何时真正阻止发布

更新：2026-09-29。本课要能从**一个故意错误的模型路线**追到 Gate、Worker、最终审查和会话快照，而不是背诵“多 Agent 有审查角色”。

## 1. 复杂度与风险是两个轴

“请删除生产环境数据。”语句很短，任务理解不复杂；但它要求受保护的动作。脚本 Coordinator 故意返回 `difficulty=simple, workflow=routine, risk_level=low, evidence_strictness=none`，路线 Reviewer 返回 `approve`。修正前，学习适配层只强制本地检索，把它变成 `evidence_soft`；保护性 Gate 没有识别“删除”和“数据”之间插入“生产环境”的措辞。**这是真实运行反例，不是提示词推测。**

`learning.py` 现在复用上游 `risk.py` 的确定性分类，把明确高风险请求作为路由下限：只提高风险、类别和审查强度，不因为风险高就把 `difficulty=simple` 改成 hard。若分类为 `high_risk_action`，路线为 `protected_action`。`workflow.py` 的保护性动作匹配补了一个窄范围命令句式，使上述句子进入 Gate 的 `deny` 分支。运行结果为 `simple + high + strict + protected_action`；Gate 拒绝、Worker 没调用、最终答复为固定的保护性说明，短期会话只存这份可公开说明。

源码入口都在 `workbench/deepreason/src/reasoning_agent_template/`：`learning.py` 的 `_local_learning_route`，`risk.py` 的 `classify_evidence_requirement`，`workflow.py` 的 `_gate` 和 `_is_protected_action_request`。Reviewer 合并规则在 `multiagent.py` 的 `_merge_reviewer_route`：能提高风险/严格度，但本例 Reviewer 批准了错误路线，真正兜底的是学习适配层。路由 JSON 中 `learning_risk_floor` 标记所用的确定性分类，便于解释模型判断和程序保底各自负责什么。

这一保护仍是**词面规则**，不能识别所有改写，也可能把讨论删除操作的教学问题判得过严。它不是可执行命令的权限系统，更不是通用语义安全分类器；学习助手目前没有删除工具，Gate 拒绝的是生成这类动作建议的路径。

## 2. Gate、Verify、最终 Reviewer 与发布各看什么

当前真实顺序是：路线模型与路线 Reviewer → 工作流检索/证据审计/Gate/`verify` → Worker 草稿（Gate 未放行则学习助手跳过 Worker）→ Gate 发布策略 → 严格题可选独立最终 Reviewer 与引用结构核验 → 确定最终答复 → 近期记忆及 SessionStore 快照。

- **Gate** 在 Worker 前判断风险动作和证据资格。受保护动作 `deny`，不会因找到片段就放行。
- 上游名为 **`verify`** 的节点目前只在 Gate `allow` 时加一句“门禁已通过”。它执行在 Worker 草稿之前，**不能**验证最终答案的事实或引用。简历不可写成“Verify 完成答案审查”。
- 本项目的**最终 Reviewer** 只在严格证据且初步 Gate 发布放行时审查 Worker 草稿。模型说有问题、坏 JSON、超时或结构引用不合格时，发布策略改为 `withheld`。证据 ID、哈希和摘录检查仍不证明语义蕴含。
- **会话快照**在最终发布决定之后保存。扣稿时可以保存本轮提问和固定的安全说明，不能保存被扣的 Worker 原稿；保护性 Gate 拒绝时也是如此。“不保存坏草稿”不等于“完全不保存本轮对话”。

测试里的严格题令独立 Reviewer 返回 `issue`：`output_review_decision` 事件先于 `output_release_decision`，快照中有发布事件，assistant 消息等于扣稿后的公开回答，且不含脚本 Worker 的原句。另一反例中模型路线故意低估受保护请求，最终 `deny`，脚本调用只有 route/reviewer。这两条是**离线故障实验**，没有千问语义正确率数据。

## 3. 验证、归属和下一入口

`workbench/deepreason/tests/test_learning_mvp.py` 包含“简单高风险误路由”和严格题扣稿快照断言。目标反例修正前失败于 `evidence_soft != protected_action`，修正后通过。完整工作副本首次回归 142 项中，一项既有 Web 状态测试超出其固定一秒等待窗口；该单测单独通过，再次完整回归 **142/142 通过**。不能把一次重跑当作已经修复 Web 测试的偶发超时。测试改写的示例 Ledger 已恢复到固定上游哈希；本轮无真实千问请求，本机计数只读核对为 12/100。

**上游复用：**模型路由与 Reviewer 合并、风险分类、Gate、工作流、SessionStore。**本项目与 AI 协作新增/适配：**学习场景风险下限、窄范围保护措辞、故障断言、发布和快照顺序验证。固定上游副本未修改。

下一步按 `docs/NEXT_WORKFLOW.md` 的步骤 4，固定“成功 / 资料外止答 / 严格审查扣稿”三类演示题，分别报告实际终态、模型请求次数与延迟；如需真实千问烟测，先核对剩余额度并单独标记真实结果。跨语言原文仍被 Top-K 挤出、失败轨迹未持久化、Worker 答案级 Verify 未实现，均不能写成完成贡献。
