# DeepReason Learning Agent

基于 [DeepReason Agents Framework](https://github.com/redmaplewww/DeepReason-Agents-Framework) 的计算机知识学习与推论助手。这个仓库保留了可运行的 Python 工作副本，并围绕多角色路由、证据交付、门禁和发布控制做小范围改造。它是 AI 应用开发的学习与评测项目，不是原框架的官方版本。

## 当前能做什么

- 在 PowerShell 中连续提问；概念解释与条件比较采用不同证据强度，所有实际生成的学习答复均经过最终审查。
- 从七份带来源的本地课程资料检索。学习场景在 `retrieve → reason` 交付前核对片段、源文件、哈希和 Evidence Ledger；资料不足时止答。
- 对明确高风险请求增加只升级的路由下限。Gate 未放行或严格题最终审查失败时，扣留草稿，只交付可公开说明。
- 路由 Reviewer 的原始回执先校验必需字段、状态和取值，再合并路线；坏 JSON、空对象、重复字段或无法应用的修订在检索和 Worker 前中断，不保存该轮会话。
- 最终审查按问题明示维度要求覆盖清单和草稿原文摘录，普通概念题至少包含直接回答与原理；程序核对清单、当前问题/草稿/证据版本与引用结构，缺项扣稿。未调用 Worker 的标准止答/拒绝不追加审查；程序不能证明语义正确。
- 对少数显式双主体比较题执行三步确定性证据计划：分别查询两个主体并汇合候选；若前四条候选排满却缺主体，最多扩大一次 Top-K，仍缺资料就跳过 Worker。任务 ID、依赖、处理器、步数与检索预算在运行前检查；源文件中途变化会阻断发布。
- 坏计划、交付契约失败与模型不可用会留下脱敏的本地失败终态；失败文件不包含问题或模型正文，也不等于自动续跑。
- 按 thread 恢复近期会话；学习入口用本地跨进程锁保护整轮读取、执行和提交，每轮重载已提交历史，快照替换失败保留旧文件。同实例或同会话忙碌时明确拒绝第二请求。本机 SQLite 在发送真实千问请求前预占名额，默认总上限为 100 次。
- 明确保存和查看本地学习笔记：写入通过上游工具门禁与 SQLite 持久回执，同一操作 ID 可在重启或响应丢失后安全核对；不会从普通提问自动写笔记。
- 对“比较题缺少成立前提”的明确反馈，可生成一条教学 Skill 候选；三例触发对照、内容哈希和旧版检查通过后，显式批准才会影响证据齐全的比较题 Worker 提示，可回退。当前仅是一个固定规则实验。

上述能力的归属及限制见[改动清单](workbench/PROVENANCE.md)和[项目状态](docs/PROJECT_STATUS.md)；下一阶段按[开发路径](docs/DEVELOPMENT_PATH.md)推进。上游的工作流、检索器和 SessionStore 是复用代码；本项目的学习场景、交付检查、发布保护及评测由维护者与 AI 协作完成。

## 运行

需要 Python 3.11+。在仓库根目录的 PowerShell 中：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_learning.py --usage
.\.venv\Scripts\python.exe scripts\learning_mvp_demo.py
```

离线演示会直接展示六题回答，再检查新进程恢复会话、笔记重复提交及 Skill 候选/审批/回退。每次保留独立的 `artifacts/demos/learning-*/`：`README.md` 是实际命令与回执，`report.json` 是完整轨迹。它使用脚本模型，不需要 API Key，不代表真实答案质量；详见[第二十八课](docs/lessons/LEARNING_28_APPLICATION_WALKTHROUGH.md)。要实际连续提问，请在**本机环境变量**中设置 `DEEPREASON_QWEN_API_KEY` 或 `DASHSCOPE_API_KEY`，然后运行：

```powershell
.\.venv\Scripts\python.exe run_learning.py
```

输入 `/usage` 查看已预占的真实请求次数，`/exit` 退出。不要把 Key 写入仓库；`.env.example` 仅列出配置名，程序不会自动读取它。`workbench/deepreason/learning_mvp/knowledge/` 是小型教学语料，并非完整计算机知识库。

学习笔记无需模型配置。先运行 `.\.venv\Scripts\python.exe run_learning.py --notes --thread note-demo` 查看当前版本；若为 0，运行 `.\.venv\Scripts\python.exe run_learning.py --save-note "复习哈希冲突" --thread note-demo --operation-id note-001 --expected-version 0` 保存，再用 `--note-receipt note-001 --thread note-demo` 核对。超时后保留原操作 ID 和正文；具体实验见[第十九课](docs/lessons/LEARNING_19_TOOL_EXECUTION_ASSURANCE.md)。笔记只按本地 thread 命名空间隔离，没有登录用户认证，也不会自动变成长期画像或 Skill。

无 Key 的 Skill 固定初态实验：`.\.venv\Scripts\python.exe scripts\eval_learning_skill_candidate.py`。它从测试笔记提出候选、拒绝过宽触发、模拟明确审批并回退，记录的是三例**触发判断**而非教学效果。手动操作及记忆边界见[第二十课](docs/lessons/LEARNING_20_MEMORY_AND_SKILL_LIFECYCLE.md)。

批准前/后七组固定初态控制流回放可运行 `.\.venv\Scripts\python.exe scripts\replay_learning_skill_paths.py`；同一语料指纹、新会话和脚本模型下核对终态、Gate、发布、模型调用和失败会话边界。结果与答案质量限制见[第二十一课](docs/lessons/LEARNING_21_PAIRED_REPLAY_BOUNDARIES.md)。

答案级离线诊断可运行 `.\.venv\Scripts\python.exe scripts\eval_learning_answers.py`。六题区分合格资料是否出现、答复字面要点是否覆盖及严格题是否扣稿；标签未经独立人工复核，字面检查不是语义准确率。缺口与发布契约分别见[第二十二课](docs/lessons/LEARNING_22_ANSWER_QUALITY_PROBE.md)、[第二十三课](docs/lessons/LEARNING_23_STRICT_ANSWER_COVERAGE_CONTRACT.md)。

三组 Skill 答案/代价对照入口为 `.\.venv\Scripts\python.exe scripts\run_learning_experiment.py`，默认只显示计划；加 `--offline` 才执行脚本实验，并在 `artifacts/experiments/` 留下六份隐藏版本标签的答复复核包与待填评分表。逐次记录角色、失败、token 与耗时，缺 usage 或人工评分时保持未测。真实千问必须显式加 `--qwen`，另有本轮请求限额；2026-10-15 实测第一条请求 HTTP 403 即停止，只新增 1 次预占，没有可评分答案。内容绑定评分与使用方法见[第二十四课](docs/lessons/LEARNING_24_PAIRED_QUALITY_AND_COST_EXPERIMENT.md)。

## 验证与边界

最简单的离线验收是在仓库根目录运行 `.\.venv\Scripts\python.exe scripts\verify_learning_paths.py`；当前十一例包含正常发布、覆盖缺失扣稿、无效路由复核和坏交付等情况，路径覆盖口径、预期结果与实测见[最小闭环测试报告](docs/MVP_TEST_REPORT.md)。运行 `.\.venv\Scripts\python.exe scripts\eval_bounded_recovery.py` 可复现相同初态下检索预算 1 次与 2 次的三组开关对照。

在 `workbench/deepreason` 目录运行离线测试：

```powershell
$env:PYTHONPATH='src'
..\..\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

最近一次完整回归及已观察的失败记录见[项目状态](docs/PROJECT_STATUS.md)。评测题与无模型诊断器分别位于 `workbench/deepreason/evals/` 和 `scripts/eval_learning_baseline.py`。当前的“语义”检索是轻量词项相似度，“Graph”是词项共现；没有 Embedding、实体多跳图谱或经过测量的全局答案准确率。比较题的计划仅支持三个确定性任务及一次有界本地补查，普通题 Planner 仍是固定文字步骤；只有一条工作流边接入运行时交付契约，名为 `verify` 的上游节点也不核验 Worker 的最终答案。

最新完整回归 **243/243**、十一例入口 **11/11**、七组 Skill 回放 **7/7**。六题和会话/笔记/Skill 操作闭环见[第二十八课](docs/lessons/LEARNING_28_APPLICATION_WALKTHROUGH.md)；修复 Skill 回退后旧候选重新有效的问题，候选同时绑定内容与单调状态修订号，旧待批候选需重新提出。普通生成正常为 4 次角色调用，标准止答/拒绝仍 2 次；真实延迟与误拦未测，盲目模型仍可能放行语义错误。发布、路由及会话保护分别见[第二十七课](docs/lessons/LEARNING_27_GUIDED_ANSWER_RELEASE.md)、[第二十六课](docs/lessons/LEARNING_26_ROUTE_REVIEW_CONTRACT.md)、[第二十五课](docs/lessons/LEARNING_25_SESSION_EXECUTION_AND_COMMIT.md)。没有问答请求幂等、排队或 checkpoint 续跑。

## 来源

- DeepReason 固定上游提交：`e98313d661527c3aa6677eec08a3b54b4ab88a33`，详情见[来源记录](UPSTREAM.md)。原仓库快照未包含 LICENSE 文件；维护者此前表示已从作者处确认 MIT 授权。这里不把上游代码写成原创成果。
- OpenDSA 教材原文及本项目中文提要的来源、固定提交、哈希与许可见 `workbench/deepreason/learning_mvp/SOURCE_MANIFEST.json`、`CURATED_SOURCE_MANIFEST.json` 和随附的 `source/OpenDSA/MIT-license.txt`。

本仓库不包含本地密钥、会话、个人记录、调用计数、原始运行产物、虚拟环境或交接压缩包；固定上游完整快照可通过上述提交获取。
