# 可修改工作副本

`workbench/deepreason/` 从固定上游 `e98313d661527c3aa6677eec08a3b54b4ab88a33` 的 142 个受版本管理文件复制。`references/deepreason-full/` 保持原样，用于对照。

截至第十五课，个人与 AI 协助改动有：

- `src/reasoning_agent_template/multiagent.py`：Worker 草稿产生后、回答净化与会话保存前调用发布策略；响应增加 `output_release` 字段，事件只记录状态，不记录被拦草稿。
- `src/reasoning_agent_template/release_policy.py`：新增确定性的最终门禁发布决策。Gate 为 `deny` / `interrupt` / 缺失时，覆盖 Worker 草稿为可公开的固定说明；Gate 为 `allow` 时仍发布原草稿，但明确标为 `released_gate_only`。
- `tests/test_release_policy.py`：新增 3 项针对性离线测试，其中 1 项贯穿完整编排器及会话保存。
- `src/reasoning_agent_template/citation_audit.py`：新增结构化引用核验器；检查 Gate、合格证据 ID、ledger/检索块哈希和摘录存在，不做语义支持判断。第九课已将其接入可选单评审路径。
- `tests/fixtures/technical_comparison.json`、`tests/test_citation_audit.py`：虚构双版本技术资料和五种结构/语义反例，新增 3 项针对性测试。
- `src/reasoning_agent_template/output_review.py`、`tests/test_output_review.py`：新增可选的单产物评审决策，严格证据且 Gate 已放行时接在 Worker 后；脚本模型覆盖正常、矛盾、坏 JSON、伪证据 ID 和超时。`multiagent.py` 再次接线并输出审查状态。
- `src/reasoning_agent_template/learning.py`、`learning_mvp/`：复用完整上游编排器实现学习场景、双路径、无资料止答、来源展示和近期会话；本地 SQLite 为真实千问调用设置跨进程 100 次硬上限。课程语料包含本项目撰写的三份 OpenDSA 中文提要，以及第十一课从 OpenDSA 官方固定版本导入的三篇英文原文；作者、许可与文件哈希见 `learning_mvp/SOURCE_MANIFEST.json`。
- 根目录 `run_learning.py` 与 `scripts/import_opendsa.py`：新增连续提问入口、无网络的已下载资料导入器。它们是个人与 AI 协助新增，不属于上游 DeepReason。
- `learning.py` 的终端输出和 `multiagent.py` 的最终 Reviewer：显示已有各角色模型调用与本地检索耗时，并补齐严格题最终 Reviewer 的计时事件；不改变路由、证据资格或模型数量。
- `tests/test_learning_mvp.py`：新增 8 项离线测试，覆盖双路径、严格审查扣稿、语料外止答、调用上限、跨进程近期会话、交互入口与长期画像不自动写入；`scripts/learning_mvp_demo.py` 生成三条脚本轨迹。
- `.gitignore`：忽略学习工作区的会话、ledger、记忆与本机调用计数；这也是工作副本相对固定上游的第二处原文件差异。
- `workbench/deepreason/evals/corpus_v1/`、`workbench/deepreason/evals/learning_questions_v1.json`、lab 根目录 `scripts/eval_learning_baseline.py`：冻结原六份资料和 12 道人工标注题；离线追踪片段存在、检索分数、过滤、Top-K、Gate 资格与 Worker 确定性放行条件。报告位于 lab 的 `artifacts/analysis/`，不是上游评测能力。
- `learning_mvp/knowledge/07_binary_tree_definition.md`、`learning_mvp/CURATED_SOURCE_MANIFEST.json`：依据 OpenDSA 官方教材新写的中文提要与来源/许可/哈希，不属于固定上游提交中的三篇 RST 导入原文。
- `evals/learning_questions_v1_binary_source_override.json`：在七文档对照里只重标原先缺失的二叉树定义题，其他标签保持不变。
- `learning.py` 的 `_explicit_comparison_subjects` 与 Worker 前检查：仅对少数显式“A和/与B有什么区别/有何不同/怎么区分”问法要求合格片段包含两个完整主体；缺失时跳过 Worker。`tests/test_learning_mvp.py` 新增三项正常/反例/补齐条件测试。它是窄范围词面覆盖检查，不是通用语义证据审查。
- `evals/learning_bilingual_v1.json` 与 lab 的 `scripts/eval_learning_baseline.py`：新增 3 道开发、2 道留出的跨语言原文锚点题及**仅评测器启用**的双语查询别名开关。实验没有接入 `learning.py`，因为留出题仍为 0/2；原始对照和试验报告在 `artifacts/analysis/`。
- `learning_mvp/configs/workflows/learning.workflow.json`、`learning.py`、`workflow_spec.py`、`workflow.py`：在学习助手专用 Spec 的真实 `retrieve_to_reason` 边标记 `local_retrieval_evidence_v1`，运行前检查 schema 位置，运行中检验本地候选、源文件行段、哈希、EvidenceItem 与 Ledger。异常在推理角色前中断。复用的是上游 Spec 解析、检索状态与 Ledger；这不是所有节点通用的契约引擎。`tests/test_learning_mvp.py` 新增正常、空检索、四种故障注入共三项测试方法。
- `learning.py` 的 `_local_learning_route` 与 `workflow.py` 的 `_is_protected_action_request`：复用上游确定性风险分类器，只对模型低估的明确高风险学习请求增加风险下限；补“请删除生产环境数据”这类目标词插在删除动词与宾语之间的窄范围保护性判定。`tests/test_learning_mvp.py` 新增故意错误的模型路线反例，并加强严格题审查扣稿与会话快照顺序断言。规则是词面保底，不能称通用语义意图/安全分类器。

当前是**发布门禁 + 可选单模型评审 + 引用结构核验**，不是经过真实测量的可靠事实审查。现有 Worker 仍会在 Gate 未通过时被调用；模型调用成本和传给模型的上下文暴露并未降低。软证据 Gate 的 `allow` 仍可能发布过度肯定的草稿；严格证据任务中的评审也可能漏判语义错误。后续需要独立标注的案例评测。

2026-10-14 针对真实额度类 403 失败，在工作副本新增以下适配与验证；固定上游未改：

- `src/reasoning_agent_template/llm.py`：为共享模型异常增加 HTTP 状态、经白名单提取的服务端错误码和可重试标志。400/401/403 等错误不重试，408/429/5xx 通常保留原有有限重试；已观察到的 `AllocationQuota.FreeTierOnly` 无论是 403 还是 429 都不重试。错误文本不回显原始服务端响应。它适用于复用的客户端和千问适配调用路径。
- `src/reasoning_agent_template/multiagent.py`：路由、复核、最终审查和 Worker 的原有最多两次尝试现在读取该标志；非重试错误第一次就退出。
- `src/reasoning_agent_template/learning.py`：单次命令行模型失败返回简短原因和退出码 2，不再打印 traceback。
- `tests/test_deepseek_client.py`、`tests/test_learning_mvp.py`：新增模拟 HTTP 状态分类、403 一次尝试、503 有界重试、无会话快照和命令行失败测试。`tests/test_multiagent_web.py` 将原先固定约一秒的异步完成等待改为最多五秒单调时钟截止；这只修订测试等待边界。

修订后完整工作副本 **147/147 项通过**，七类学习终态离线验收 **7/7 通过**，Web 单测重复 **10/10 通过**。本次真实千问请求 **0 次**，本机预占数仍为 **14/100**；修复尚未经真实额度恢复后的调用检验。旧 Web 测试通过也不等于已证明无运行时竞态。示例 Ledger 已恢复并与固定上游哈希一致。

历史记录：第十五课后完整工作副本第二次回归 **142 项通过**（固定上游 118 项 + 当时新增 24 项）；第一次一项旧 Web 状态测试超出固定一秒窗口，单测和再次完整回归均通过。当时没有真实千问请求，计数为 **12/100**。双语别名未部署；契约失败不会继续 Worker 或保存会话，但检索已可能写 Ledger，失败轨迹也尚未持久化。通用上游配置的单产物评审仍默认关闭，学习助手只在严格题启用；上游 `verify` 节点不做 Worker 答案核验。真实语义准确率、额外 token/延迟及一次修订尚未测量/实现。完整测试会修改工作副本内的示例 `evidence/ledger.jsonl`；后续重测应恢复它，保持差异清晰。
