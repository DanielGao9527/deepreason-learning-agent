# 第十四课：双语检索失败实验与一条真实节点交付边

更新：2026-09-29。学习目标是分清**候选检索、证据资格和运行时交付**三个判断，不把一次失败的查询改写包装成检索优化，也不把 Spec 里的文字字段包装成运行时契约。

## 一、源码现在怎样工作

固定上游的 `knowledge.py` 将 BM25、轻量词项相似度和词项共现图的分数合成候选，`workflow.py` 在 `retrieve` 节点把候选和 EvidenceItem 放进状态，EvidenceLedger 记录来源。实际下一条边是 **`retrieve -> reason`**，之后才是 `evidence_audit -> gate`。因此如果想防止损坏的检索结果流向推理角色，校验必须发生在 `retrieve_to_reason`，不是在想象中的 `retrieve -> evidence_audit`。上游 Workflow Spec 有 `handoff_contract` 字段，但原来只保留配置，不执行这项本地证据一致性校验。

## 二、双语别名为什么没有上线

先冻结 `workbench/deepreason/evals/learning_bilingual_v1.json`：三道开发题、两道新留出题，每题标注一段英文 OpenDSA 原文。`scripts/eval_learning_baseline.py` 只在 `--expand-query` 实验开关下给中文问题补少量英文别名，例如“哈希”附加 `hashing hash table`。语料、Top-K=4、最低分和 Gate 资格阈值保持一致；报告保留文件与代码哈希。这个开关**没有接入学习助手的正式查询链**。

| 条件 | 开发题标注原文取得 Gate 资格 | 新留出题 | 原 12 题留出集 |
| --- | ---: | ---: | ---: |
| 原查询 | 0/3 | 0/2 | 原基线 0/3 |
| 仅评测器补双语别名 | 1/3 | 0/2 | 0/3 |

报告依次为 `artifacts/analysis/learning_bilingual_before_2026-09-29.json`、`learning_bilingual_alias_v1_2026-09-29.json`、`learning_v1_alias_regression_2026-09-29.json`。别名使一些英文片段从零分或最低分过滤进入有分候选，但短中文提要仍占据 Top-4；也就是说“查到了候选”与“标注依据进入最终证据”不是一回事。新留出两题均无改善，所以拒绝部署。原 12 题的留出锚点仍是 0/3，不能声称整体质量变好。这组题很小，只用于定位失败，不是总体召回率估计，也未测千问答案正确率。

可离线复现：

```powershell
.\.venv\Scripts\python.exe scripts\eval_learning_baseline.py --cases workbench\deepreason\evals\learning_bilingual_v1.json --output artifacts\analysis\recheck_before.json
.\.venv\Scripts\python.exe scripts\eval_learning_baseline.py --cases workbench\deepreason\evals\learning_bilingual_v1.json --expand-query --output artifacts\analysis\recheck_alias.json
```

## 三、真正执行的交付契约

学习场景专用 `learning_mvp/configs/workflows/learning.workflow.json` 在 `retrieve_to_reason` 标记 `local_retrieval_evidence_v1`；`learning.py` 选择这份 Spec，`workflow_spec.py` 拒绝未知 schema 或把本 schema 配到错误边。`workflow.py` 在检索节点产出后、状态展示和 Reasoner 消费前执行校验：

1. 候选与 EvidenceItem 必须是正确容器和类型；每块要有来源、行段、文本、证据 ID、哈希与有限数值分数。
2. 来源必须仍在学习知识目录内；当前文件的行段内容与候选文本完全一致，文本哈希吻合。
3. 每个候选的证据 ID 在本轮 EvidenceItem 和 EvidenceLedger 中都存在，URI、行段、内容哈希及记录内容一致，且集合没有多余或重复 ID。
4. 空候选本身可以交付，随后原有证据/发布流程仍必须止答。校验通过时记录 `handoff_validated`，只放 ID、数量和摘要哈希，不把原文写进事件。

**正常案例：**“什么是哈希冲突？”取得候选，`handoff_validated` 发生在 Worker 前，脚本 Worker 能继续。**无资料案例：**空候选通过“结构合法”检查，但没有证据资格，Worker 不调用。两者说明交付合法不等于证据充分。

**故障案例：**测试分别改坏候选证据 ID、内容哈希、源文件当前文本和候选对象类型；四类均抛带 `reason_code` 的 `WorkflowContractError`，脚本模型只有 route/reviewer 调用，Worker 不调用，线程的 session snapshot 不生成。类型损坏还揭露了一个顺序问题：若先发 `stage_completed` 给展示层，展示层会因无效对象先崩溃；现在检索后先校验，再发完成事件。相关测试在 `tests/test_learning_mvp.py`，完整工作副本 **141 项离线测试通过**。

## 四、归属、边界与下一课

**上游复用：**Workflow Spec 解析、状态机、Retriever、EvidenceLedger、SessionStore 和原有 Gate。**本项目与 AI 协作新增：**实验评测器/题集、学习专用 Spec、这一条边的校验和故障测试。固定上游副本未修改。

这不是通用 Schema 引擎：只检查本地检索到推理的一条边；它验证来源一致与结构，不证明资料语义支持答案。检索阶段可能已写 Ledger，异常时只保证 Worker 不继续、会话不保存；`handoff_rejected` 尚无持久失败轨迹，不能宣称完整回放或零副作用。没有真实千问请求，最近核对为 12/100。下一课按 `docs/NEXT_WORKFLOW.md` 测简单但高风险问题的路由，并核对 Gate、最终 Reviewer、发布与会话保存先后顺序；跨语言 Top-K 排序失败另作单因素实验。
