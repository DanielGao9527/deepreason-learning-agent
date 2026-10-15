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

第十六课在工作副本新增有限比较题计划，固定上游未改：

- `src/reasoning_agent_template/learning_plan.py`：个人与 AI 协作新增三任务证据计划及检索前校验，限制为两个主体查询和依赖它们的证据汇合；校验缺依赖、循环、不可用处理器与三步上限。没有模型生成计划或自动重规划。
- `src/reasoning_agent_template/learning.py`：新增 `LearningTemplateCoordinator`，让上游本地检索器分别消费两个主体 query、筛选包含主体的候选并汇合证据 ID；缺一侧时学习 Worker 止答。其他题继续使用原上游检索路径。
- `src/reasoning_agent_template/multiagent.py`、`models.py`：在原编排器加入可覆盖的 Coordinator 构造钩子，并把本轮执行计划保存到状态与工作流输出；这不是重写工作流引擎。
- `tests/test_learning_mvp.py`、`scripts/verify_learning_paths.py`：记录实际 Retriever 查询、正常与资料缺失结果，故障注入坏计划并检查检索/Worker/会话边界；七类终态验收增加计划状态断言。

本轮学习场景 **21/21**、完整工作副本 **148/148**、七类离线验收 **7/7** 通过，真实千问请求 **0**；尚无真实答案质量或延迟改善数据。工作流 Spec 的 14 条边仍只观察到 9 条，比较计划运行于 `retrieve` 节点内部，不增加完整节点路径。详见 lab 的 `docs/lessons/LEARNING_16_REACHABILITY_AND_BOUNDED_PLAN.md`。

第十七课继续在完整工作副本做小范围适配，固定上游未改：

- `src/reasoning_agent_template/multiagent.py`：异常路径增加默认空实现的失败记录钩子，并保证记录失败不遮盖原异常；其他上游场景不自动写文件。
- `src/reasoning_agent_template/learning.py`：学习场景把坏计划、交付契约失败、模型不可用分成受控终态，原子写入忽略版本控制的 `learning_mvp/local_state/failures/`。记录只保留控制流元数据；没有原始问题、thread ID、模型正文和服务端错误原文。未分类异常的会话写入状态标为未知。
- `tests/test_learning_mvp.py`、lab 的 `scripts/verify_learning_paths.py`：故障注入并核对失败文件、原有停止边界、隐私字符串不落盘、重新构造对象后的持久性，以及诊断写盘故障不改变原异常。

本轮学习场景 **23/23**、完整副本 **150/150**、七类离线验收 **7/7**；真实千问 **0** 次，本机预占 **14/100**。这项只让异常可复查，**未实现自动恢复或完整回放**；检索阶段的 Ledger 写入仍可能先于交付失败。详见 lab 的 `docs/lessons/LEARNING_17_FAILURE_TERMINALS.md`。

第十八课新增有限 Top-K 补查，固定上游未改：

- `src/reasoning_agent_template/learning_plan.py`：比较题计划新增每主体最多两次本地检索与扩展 Top-K 上限，运行前校验越界预算。
- `src/reasoning_agent_template/learning.py`：只在初次候选达到 Top-K 且没有完整比较主体时，用同一 query、同一分数门槛扩大一次候选；记录每次候选数与主体命中。对本地资料建立文件字节指纹，检索后和 Worker 前复查；源变化、检索超时分别归类为脱敏失败终态。
- `src/reasoning_agent_template/multiagent.py`：在发布、记忆写入与会话保存之前新增默认空钩子；学习场景在此复查资料指纹，阻止 Worker 或最终审查期间出现的迟到旧答发布。其他上游场景保持默认行为。
- `tests/test_learning_mvp.py`、lab 的 `scripts/verify_learning_paths.py` 和 `scripts/eval_bounded_recovery.py`：构造真实排序的 Top-K 干扰语料，验证一次补查、真缺资料止答、预算限制、源变化、超时和迟到 Worker；三组同初态预算 1/2 离线开关对照记录模型与本地检索调用数。

学习场景 **30/30**、完整副本 **157/157**、八例验收 **8/8**；真实千问 **0**，本机预占 **14/100**。唯一得到恢复的夹具从止答变回答，额外本地检索一次、额外脚本模型 Worker 一次；不能当作答案准确率或性能提升。恢复仍局限于显式双主体比较题和 Top-K 截断，不是通用任务恢复、语义查询重写或跨进程事务。详见 lab 的 `docs/lessons/LEARNING_18_BOUNDED_RETRIEVAL_RECOVERY.md`。

历史记录：第十五课后完整工作副本第二次回归 **142 项通过**（固定上游 118 项 + 当时新增 24 项）；第一次一项旧 Web 状态测试超出固定一秒窗口，单测和再次完整回归均通过。当时没有真实千问请求，计数为 **12/100**。双语别名未部署；契约失败不会继续 Worker 或保存会话，但检索已可能写 Ledger，失败轨迹也尚未持久化。通用上游配置的单产物评审仍默认关闭，学习助手只在严格题启用；上游 `verify` 节点不做 Worker 答案核验。真实语义准确率、额外 token/延迟及一次修订尚未测量/实现。完整测试会修改工作副本内的示例 `evidence/ledger.jsonl`；后续重测应恢复它，保持差异清晰。

第十九课把上游独立 Tool Runtime 用于明确学习笔记动作，固定上游未改：

- `src/reasoning_agent_template/runtime.py`：复用原有工具注册、Schema、Gate、路径限制与超时框架；本项目加固定目标路径、额外字段拒绝、只读最多一次超时重试，以及写超时/未知异常后的匹配回执核对。回执不确定时停止自动重试。上游其他工具的进程内去重仍不具持久保证。
- `src/reasoning_agent_template/learning_notes.py`：本项目与 AI 协作新增本地学习笔记读写。SQLite 事务把 `(thread_id, operation_id)` 的唯一笔记、版本与回执同时提交；同 ID 换正文、旧版本和并发竞争不会产生第二条笔记。回执核对同时比较正文与哈希。
- `src/reasoning_agent_template/learning.py`、`tests/test_learning_notes.py`：增加显式命令行读、写、查回执和离线故障注入；命令适配使用确定性模型桩走上游 Runtime，普通学习问答**没有**自动 tool calling。`.gitignore` 忽略本地笔记库；不把个人笔记加入仓库。

针对性测试与完整回归的最终结果见 lab 的 `docs/lessons/LEARNING_19_TOOL_EXECUTION_ASSURANCE.md`。这是一种**单场景适配**，不能写成通用 MCP 工具层、任意写工具持久幂等或完整长期记忆。

第二十课以第十九课的明确笔记作为来源，新增一个**固定比较题规则**的 Skill 候选实验，固定上游未改：

- `src/reasoning_agent_template/learning_skill.py`：本项目与 AI 协作新增候选/版本 SQLite。候选记录来源笔记 ID/正文哈希、旧版与新内容哈希；固定三例检查正常、缺证据、非比较题。显式批准时重算内容、来源与评测并核对旧版，复用上游 `GatePolicy` 检查 `update_skill` 审批、来源证据及工作区目标；回退按当前哈希再过审批 Gate 切回旧版。只有允许列表中的固定教学指令可以进入系统提示。
- `src/reasoning_agent_template/learning.py`：只在比较计划完成、Gate 放行且有合格证据时，将已批准规则加入 Worker system prompt；命令行增加查看、从笔记提案、哈希绑定批准和回退。它没有扩展上游 `SkillRegistry` 为通用加载器，亦不让模型自主修改 Skill。
- `tests/test_learning_skill.py`、lab 的 `scripts/eval_learning_skill_candidate.py`：正常/前提变化/反例、过宽触发、内容或评测被改、来源错误、旧版冲突、完整脚本问答批准前后及回退后的 Worker 提示，均离线核验。固定三例 2/3→3/3 仅是触发判断，不是答案正确率；真实千问 0。

上游 `memory.py` 的短/长期结构、`skills.py` 的元数据发现及 `evolution.py` 的仅提案 JSON 属于原有代码；本项目只是核对并记录边界。完整源码和限制见 lab 的 `docs/lessons/LEARNING_20_MEMORY_AND_SKILL_LIFECYCLE.md`。

第二十一课增加 lab 级离线配对回放，固定上游及工作副本运行策略均未改：

- `scripts/replay_learning_skill_paths.py`：本项目与 AI 协作新增每题两份全新工作区的控制流对照。拷贝相同课程语料并校验 SHA-256，固定脚本模型与明确反馈笔记，仅切换 Skill 是否已获哈希绑定批准；核对七类终态、Gate、发布、模型调用、阶段轨迹、会话快照，以及坏交付失败记录。报告保存 run ID、耗时与原始逐例结果在忽略版本控制的 `artifacts/analysis/`。
- 结果是 **7/7** 配对终态符合预期、意外控制流变化 **0/7**、目标 Worker 提示加载 **1/7**、脚本模型调用差 **0**；真实千问 0。这是控制流回归，不是答案语义正确率或性能提升。

原理、复现和局限见 lab 的 `docs/lessons/LEARNING_21_PAIRED_REPLAY_BOUNDARIES.md`。

第二十二课新增**离线答案诊断**，固定上游与正式学习运行策略未改：

- `src/reasoning_agent_template/answer_eval.py`、`evals/learning_answer_probe_v1.json`：本项目与 AI 协作新增小型题目要点和分层归因器，分别看预期终态、合格检索片段中的资料锚点及答案字面要点。标注未经过独立人工复核，字面匹配不是语义验证。
- lab 的 `scripts/eval_learning_answers.py`、`tests/test_learning_answer_probe.py`：用真实工作流和固定脚本模型跑新会话，保存逐题证据与结论；校准测试特意展示“关键词齐全但含义颠倒”仍会误过代理检查。

六题终态 6/6，四题合格资料锚点 4/4，但脚本答案字面要点 0/4；两题按预期止答 2/2。此结果暴露当前固定脚本答案的教学内容缺口，**不是千问准确率，也不是 Skill 前后收益**。本课真实千问调用 0。详见 lab 的 `docs/lessons/LEARNING_22_ANSWER_QUALITY_PROBE.md`。

第二十三课在完整工作副本中新增**学习严格题答案覆盖契约**；固定上游未改：

- `src/reasoning_agent_template/learning.py`：本项目按问题明示维度生成有界清单，普通 guided 路径不启用。
- `src/reasoning_agent_template/multiagent.py`、`output_review.py`：本项目在原独立 Reviewer 调用与引用结构审计上加可覆盖钩子、清单交付、草稿/清单上下文哈希回执及逐项摘录核验。通用上游风格场景无清单时保留既有行为。
- `tests/test_learning_mvp.py` 与 lab 的三份离线脚本：完整正例、supported 但缺清单、重复/伪造摘录、缺项、标未覆盖和旧回执，均通过实际 Worker→审查→发布→会话路径验证；离线路径增加一例扣稿反例。

完整副本 **189/189**，九类学习路径 **9/9**，七组 Skill 配对 **7/7**，真实千问 0。契约核验结构与本轮版本，不证明语义正确；来源及讲解见 lab 的 `docs/lessons/LEARNING_23_STRICT_ANSWER_COVERAGE_CONTRACT.md`。

第二十四课新增**有界配对质量/代价实验与内容绑定人工评分**，固定上游和正式问答策略未改：

- src/reasoning_agent_template/learning_experiment.py：本项目与 AI 协作新增底层调用尝试计量、本轮请求上限、不可重试错误封闭、模型标签一致性、usage 白名单与缺失标记；人工复核包隐藏版本标签，并用实验/答案/证据哈希阻止旧评分误用。
- lab 的 scripts/run_learning_experiment.py：复用现有 LearningAssistant、Qwen SQLite 全库预占、笔记与 Skill 审批，固定三组题的语料、Workflow、代码指纹和新会话；默认计划、显式离线或千问执行，失败实验不生成质量对照。真实千问模式尚未实测。
- tests/test_learning_experiment.py：17 项针对性测试；完整副本 206/206。正常离线 16 次（route 6、reviewer 6、worker 4）且 Skill 加载 1 次，限额 2 时只转交 2 次、拒绝第三次。六份答复未独立评分，token 与真实效果未测，千问调用 0。

课程及评分方法见 lab 的 docs/lessons/LEARNING_24_PAIRED_QUALITY_AND_COST_EXPERIMENT.md；未把模拟评分或未知 usage 写成真实收益。

第二十五课新增**学习入口的本地会话执行与提交保护**，固定上游未改：

- `src/reasoning_agent_template/learning_sessions.py`：继承上游 SessionStore 的格式、路径校验和加载；新增稳定路径哈希锁文件、Windows/Unix 非阻塞文件锁和临时快照替换。只有 Windows 分支完成实际测试。
- `learning.py`：学习编排器增加实例互斥、整轮会话锁、获锁后的历史重载及退出时清理缓存；学习助手使用新存储适配器，CLI 与交互模式友好返回忙碌。上游 `multiagent.py`、`sessions.py` 未因本课修改。
- `tests/test_learning_sessions.py`：14 项故障/回归测试；A→B→A 三轮改前快照只剩 2 轮，改后保留 3 轮，第三轮路由消费前两轮；包含跨进程提交/竞争、Worker 阶段终止进程与替换失败。完整副本 220/220，九例入口 9/9。

同轮真实千问对照在第一条 route 请求 HTTP 403 后停止，无评分包；仓库预占 14→15/100。会话增强的实现和测试均无额外真实模型调用。课程及限制见 lab 的 `docs/lessons/LEARNING_25_SESSION_EXECUTION_AND_COMMIT.md`；不宣称通用并行平台、问答幂等或 checkpoint 续跑。

第二十六课完成现行 S1.1 的**学习路由复核输出契约**，固定上游未改：

- `multiagent.py`：只新增 `_parse_route_review` 可覆盖入口；通用调用继续原宽松解析，原模型重试和只升级合并复用。
- `learning.py`：本项目与 AI 协作新增原始回执 JSON/必需字段/枚举/列表/数值/重复键校验、未应用修订中断、`LearningRouteReviewError`、`route_review_failed` 脱敏终态和 CLI 接线；校验位于默认归一化之前，格式错误不重试。
- `tests/test_learning_route_review.py`、lab 的 `scripts/verify_learning_paths.py`：新增 9 项测试（含 32 种坏回执和 2 种不可应用修订），一键验收增加坏复核中断。三类已复现故障改前均调用 Worker/保存，改后均在检索前停止且保留旧历史。完整 229/229、入口 10/10。

本轮千问真实请求 0，预占仍 15/100，示例 Ledger 已恢复至上游哈希。真实格式兼容和误拦未测；普通题最终审查是下一包 S1.2，未提前标完成。完整范围及教学说明见 lab 的 `docs/lessons/LEARNING_26_ROUTE_REVIEW_CONTRACT.md`。

第二十七课完成 **S1.2 普通生成答案最终发布保护**，固定上游未改：

- `multiagent.py`：本项目新增 `_should_review_output` 场景钩子，通用入口保留原严格题触发策略；实际审查前设置 output_review 活动阶段，修复共享重试事件记录异常原文的问题，改留错误类型/有效 HTTP 状态。
- `learning.py`：学习入口对实际调用 Worker 的所有草稿强制复用已有最终 Reviewer/引用/覆盖/上下文哈希审计，跳过 Worker 的标准说明不增加审查；比较计划在复核前再次检查源版本。没有增加异构模型或语义证明算法。
- `tests/test_learning_guided_review.py`：10 项测试含 13 种审查失败、预算不足、重试、源块哈希及发布时序，另保留“盲目 supported 仍放行错误语义”的限制案例。`test_learning_mvp.py` 保留原空泛反例，另写明确正常脚本；其余会话/Skill/路由测试更换正常样例及新增调用预期，未以删掉旧反例取得通过。
- lab 的现有验收/回放/补查/实验/答案探针脚本同步调用代价和明确样例；旧坏脚本的四份生成草稿现在均扣留，目标终态匹配 3/6 不称模型准确率。三组配对脚本从 16→20 次，六份最终答复待评分。

完整 **239/239**、入口 **11/11**、七组配对 **7/7**；正常普通生成请求 3→4、标准止答仍 2。原三道空泛题改前发布 3/3、改后扣留 3/3，明确正常样例另测发布 3/3。真实千问 0，预占 15/100，示例 Ledger 已恢复。真实语义/误拦/延迟待 S2；课程见 lab 的 `docs/lessons/LEARNING_27_GUIDED_ANSWER_RELEASE.md`，下一入口 S1.3。


第二十八课 / S1.3 在现有应用接口上完成六题与状态操作验收；固定上游未改：

- `learning_skill.py`：本项目新增 SQLite 状态 revision 与候选 base_revision；同一事务内校验基础内容/修订号，批准和回退都推进修订。旧库迁移保留活动版本，旧待批候选重新提出。修复回退后基础哈希恢复使旧候选意外有效的问题。
- `tests/test_learning_skill.py`：新增四项行为回归，覆盖 ABA、同内容新版本、旧库迁移与提出期间的交错变更；原审批/来源/触发/提示测试保留，定向 15/15。
- `scripts/learning_mvp_demo.py`：扩展原三题入口，复用已有学习助手、真实检索/发布、会话存储、笔记/Skill CLI 与明确正例脚本；六题和跨进程操作均留文件、回执及完整 payload。未增加生产工具、Agent 或自动自进化。

完整 243/243（211.181 秒）、入口 11/11、七组 Skill 回放 7/7；演示六题 6/6、44 次脚本调用和 19 条 CLI，真实千问 0、预占 15/100。示例 Ledger 恢复上游哈希。路由/生成/复核是脚本，不证明真实质量或速度；下一项 S2.1 真实验收，最终停止边界见 `docs/DEVELOPMENT_PATH.md`。


第二十九课 / S2.1 在真实 qwen-max 验收中修复目标/查询与审查输入边界，固定上游未改：

- `learning.py`：默认模型 qwen-max；学习 Workflow 使用原始问题，改写只在只读检索期间使用，异常恢复原目标；路由提示使用合法示例/独立允许值，Reviewer 只消费 ROUTE_KEYS 业务字段。
- `multiagent.py`：新增可覆盖目标选择入口，通用调用保持旧选择行为；最终审查补精确回执示例。未放宽 JSON、引用、覆盖或扣稿规则。
- `tests/test_learning_goal_boundary.py`：六项新增回归覆盖改写绕过门禁、比较计划、正常 query 消费、异常、协议和输入投影。真实危险路由回执离线重放 allow→deny、4→2 次角色调用；只保护学习入口，不称所有上游场景已修复。
- `.env.example`、README 和课程：可运行模型、真实失败及当前边界。受控公开题回执/原始运行产物仅在本地 artifacts，不含凭据，不提交 Git。

完整 249/249（101.876 秒）、入口 11/11、七组回放 7/7。真实本轮 52 次，累计 67/100；真实同版本六题仅 2/6 符合原终态，尚未通过全部验收。后续双题复测因一次重试耗尽 8 次限额而 aborted；不作质量对照。51 次已知 usage 输入 61772 / 输出 12588，缺失不补零。服务已通，仍需真实协议/引用稳定性和独立复核；不宣称效果或提速。
