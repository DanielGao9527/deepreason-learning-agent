# 第九课：把单个产物评审接到真实编排链

更新：2026-09-25。代码在 `workbench/deepreason/src/reasoning_agent_template/`：`multiagent.py` 的 Worker 调用之后、回答净化和会话保存之前，接入 `output_review.py`，再调用上一课的 `citation_audit.py`。固定上游未改。本轮全部为**脚本模型和合成资料离线验证**，没有调用千问。

## 一次严格证据任务现在怎样走

Coordinator 和原 Reviewer 仍先决定路线，工作流检索、审计并产生 Gate。Worker 先给草稿；第七课的发布策略立刻判断 Gate，非 `allow` 直接扣住草稿。当 `config.runtime["output_review_enabled"] = True`、证据模式为 `required`、严格度为 `strict` 且 Gate 已 `allow` 时，再调用一次 `critic` 模型做**最终答案评审**。这个开关目前默认关闭，便于保持原有轻量和软证据路径；启用场景见 `tests/test_output_review.py`。

评审收到原问题、Worker 草稿及至多 8 个本轮合格证据块，必须返回 JSON：

```json
{
  "review_status": "supported",
  "coverage_complete": true,
  "findings": [],
  "claims": [{
    "claim_id": "c1",
    "statement": "一个关键结论",
    "evidence_id": "ev_...",
    "excerpt": "从对应证据块原样复制的摘录"
  }]
}
```

程序只在模型报告 `supported`、报告覆盖全部关键结论、没有问题项且**每条引用经过上一课的结构核验**时发布草稿，并标为 `released_model_reviewed`。这表示“模型报告支持 + 引用结构过关”，**不表示语义事实被程序证明**。模型若报告 `issue` / `uncertain`、返回坏 JSON、引用伪 ID、调用失败或超时，统一扣住草稿并给出不含原草稿的说明；会话也只保存公开说明。审查调用最多一次普通尝试和一次失败重试，没有无界循环，本轮**尚不做修改草稿再审**。

## 离线实验真正证明了什么

`tests/test_output_review.py` 走完整编排器：脚本 Coordinator 给严格学术路线，原 Reviewer 批准，外部检索用两份虚构 FlowRelay 版本资料，Gate 获得两条合格 paper，Worker 产出草稿，新增评审再判断。正常脚本评审附合格 ID 和原文，回答发布，调用顺序为 Coordinator → 路线 Reviewer → Worker → 产物 Reviewer。四个失败替身分别报告矛盾、返回坏 JSON、使用伪证据 ID、模拟超时；四例都没有把脚本 Worker 的 `UNVERIFIED` 草稿写入响应或 SessionStore。

新增 2 项集成测试通过；工作副本完整离线回归 **126 项通过**（固定上游 118、前两次新增 6、本轮新增 2）。测试后已恢复工作副本中的示例 ledger。`artifacts/validation/output-review-2026-09-25.json` 记录命令和范围。默认关闭的旧路径仍在完整回归中通过，但这不是开关打开后的真实模型质量证明。

## 最重要的剩余漏洞与下一步

`coverage_complete` 是评审模型自报。它可能漏列草稿中的某个结论，或者拿真实摘录给出相反解释；上一课两个语义错误案例已经说明，结构核验会让它们通过。单评审与 Worker 还可能共享模型偏差。所以不能在简历写“已实现可靠事实验证”或任何改进率。

下一步需在固定案例集上做原版、发布门禁、单评审三种对照：人工逐条标注支持/矛盾/条件遗漏，数**正确完成、错误发布、弃权、额外调用和耗时**。若单评审确实降低错误发布且没有过度弃权，再考虑一次定向修订；每次修改后必须重新审查，不能让修订绕过 Gate。动态权重和多评审团仍无足够数据支撑，暂不增加。

复现：在 `workbench/deepreason/` 下把其 `src` 设为 `PYTHONPATH`，执行 `python -m unittest discover -s tests -p test_output_review.py -v`；完整回归用 `python -m unittest discover -s tests -v`。使用本项目 `.venv` 的 Python 即可，无需 API Key。
