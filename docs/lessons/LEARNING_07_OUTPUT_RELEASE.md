# 第七课：为什么 Gate 通过与答案发布之间还要有一道代码判断

更新：2026-09-25。这堂课有实际代码改动，位于 `workbench/deepreason/`，固定上游 `references/deepreason-full/` 未改。目标是解决已观察到的一个具体矛盾：工作流 Gate `interrupt` / `deny` 后，完整编排器仍调用 Worker，并原样把其自然语言草稿作为 `payload["answer"]` 交付。

## 现有链路与改动位置

在上游 `multiagent.py` 的 `run` 中，`TemplateCoordinator.run` 先产生 `GateDecision`，随后 `_call_deepseek` 生成 Worker 草稿。原版只做 `_sanitize_answer_for_user`，再保存到短期记忆和会话快照，最终放入响应。净化函数去掉内部证据 ID，不检查 Gate 状态或结论真假。

工作副本在 Worker 草稿之后、净化和持久化之前调用 `release_policy.decide_release(draft, gate_decisions)`。它只看**最后一次 Gate 状态**：

| Gate | 对外回答 | `output_release.status` |
| --- | --- | --- |
| `allow` | 维持原草稿 | `released_gate_only` |
| `interrupt`、`deny`、缺失 | 用固定说明覆盖草稿 | `withheld` |

拒绝时事件与响应只记录状态和原因代码，不记录被拦的 Worker 原文。会话快照保存的是覆盖后的公开回答。它不是依靠第二个模型“自觉克制”，因而脚本 Worker 即便故意给出确定结论，`payload["answer"]` 也不会放出这段文字。现有流程仍会调用 Worker；减少不必要模型调用是另一项改动。

## 已验证的边界

新增 3 项测试：直接覆盖 `interrupt`、`deny`、缺失 Gate 与 `allow`；完整编排器在高风险、零证据、Gate 中断时，让脚本 Worker 返回 `UNVERIFIED_CLAIM`，核对响应和 SessionStore 都不含它；普通轻量问答 Gate 允许时原文保留。工作副本完整离线回归 **121 项通过**（原有 118 + 新增 3），没有访问千问或外部网络。测试中的示例 ledger 变动已恢复，实际与上游不同的既有文件仅 `multiagent.py`。

这证明的是**Gate 未允许时不发布 Worker 草稿**，不是“最终报告已事实核查”。当前软证据策略可以在资料不足时返回 `allow`，产物仍交给模型自我约束。Gate 允许时的两条证据也可能重复、过期或不支持某一具体结论。下一阶段应围绕两份有版本的技术资料建立可人工核对的案例，把关键结论、引用 ID 和摘录交给单个产物评审；程序校验引用归属和摘录存在，再比较错误发布、正确完成、弃权与调用代价。任何审查结果都不能把原 Gate 的 `deny` 改成 `allow`。

## 怎样理解这项贡献

上游的多角色调度、Gate、会话保存均直接复用；新增的是**发布决策模块及在编排器中的接线**。这是一个小但真实可验证的改动，不能包装成完整评审团、语义事实审查或自学习。代码归属与未解决的问题见 `workbench/PROVENANCE.md`。

在 `workbench/deepreason/` 中以该副本的 `src` 为 `PYTHONPATH` 运行 `python -m unittest discover -s tests -p test_release_policy.py -v` 可只看本课三例；完整回归使用 `python -m unittest discover -s tests -v`。Windows 下可用本项目的 `.venv/Scripts/python.exe`。不要把 `references` 与 `workbench` 同时放进同一 Python 进程的导入路径。
