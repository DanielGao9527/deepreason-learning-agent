# 第八课：引用真的存在，与结论真的成立，是两道不同的题

更新：2026-09-25。本课只完成**结构化引用协议与机械核验器**，位置在 `workbench/deepreason/src/reasoning_agent_template/citation_audit.py`。它还没有接进 `MultiAgentOrchestrator.run`，也没有真实 Reviewer 模型。五个脚本审查对象和两份虚构 FlowRelay 版本资料在 `workbench/deepreason/tests/fixtures/technical_comparison.json`；结果见 `artifacts/analysis/citation_fixture_results.json`。

接续状态：第九课已把这个核验器接进**可选的**单产物评审路径；本课下文保留第八课完成时的实验边界，完整链路见 LEARNING_09_SINGLE_OUTPUT_REVIEWER。

## 给单个产物评审的最小协议

Worker 草稿之后，评审者应逐项返回 `{claim_id, statement, evidence_id, excerpt}`。这里的 `statement` 是草稿中的关键结论，`evidence_id` 指向本轮**合格**证据，`excerpt` 是声称支持它的原文。结构化字段让程序能核对来源，而不靠评审者只写“我认为正确”。

`audit_claim_citations` 按顺序执行四个约束：

1. 原 Gate 必须 `allow`；评审不能投票或打分覆盖 Gate。
2. 至少提交一条格式完整的结论；同一 `claim_id` 不能重复。
3. 每个引用 ID 必须在本轮 `qualified_evidence_ids`，且能同时找到 ledger 记录和当前检索块。
4. 检索块正文哈希、ledger 内容哈希和块内存的哈希一致，摘录必须原样出现在该块正文中。

任一规则失败返回 `blocked` 和具体原因。全部满足也只返回 `structurally_valid_semantics_unchecked`，**没有 `publish` 结论**。这不是为了拗口，而是避免把“引用找到了”误当“引用支持了观点”。

## 五个案例暴露的边界

| 案例 | 机械核验结果 | 案例设计时的预期判断（尚非独立人工标注） |
| --- | --- | --- |
| v2.2 的去重需要开启选项并提供 request ID，引用相符 | 结构有效 | 条件在资料中 |
| v2.2 结论却引 v2.1，摘录不在该来源 | 阻断 | 引用错位 |
| 声称默认去重，摘录是捏造的 | 阻断 | 引用伪造 |
| 摘录确实写着“必须开启并提供 ID”，结论却说“默认开启且不需 ID” | **结构有效** | **明显矛盾**，程序尚未检出 |
| v2.1 用 4 核测得 700，v2.2 用 8 核测得 910，结论说软件使吞吐提高 30% | **结构有效** | **比较条件不同，不能归因软件** |

后两行正是下一阶段单评审要处理的语义问题。即便再加多数投票，若各评审都忽略“必须开启”和核数差异，错误仍可能被一致赞成。需要让评审明确标注**支持、矛盾、证据不足、条件遗漏**，并在人工标注案例上量化其误判；代码仍独立核验引用归属。

## 这份协议尚有三个缺口

- 当前核验器只检查**评审提交的结论**，不知道它是否遗漏 Worker 草稿里另一句关键断言。后续需有句子/结论覆盖检查或独立复核。
- 精确摘录匹配故意严格；同义改写、换行差异会被拦。这有利于第一轮审计，但评测要记录误拦，不凭直觉放宽。
- ledger 记录了内容哈希，但不能证明来源本身真实、最新或独立；不同硬件基准也需要任务级语义判断。

本轮新增 3 项测试通过，覆盖五个案例的预期结构状态、Gate/资格不能被覆盖，以及缺失或篡改来源时阻断；脚本生成的五案例汇总也通过断言。**没有重新跑工作副本完整 121 项**，因为新模块尚未接进运行主链。下一步先定义单评审的语义标签及失败/超时返回，再接入现有 `release_policy` 的 `released_gate_only` 路径，限定最多一次修订。接入后才需要完整回归与原版对照。

复现：项目根目录运行 `.\.venv\Scripts\python.exe scripts\evaluate_citation_fixture.py`；单测在 `workbench/deepreason/` 中以其 `src` 为 `PYTHONPATH` 运行 `python -m unittest discover -s tests -p test_citation_audit.py -v`。
