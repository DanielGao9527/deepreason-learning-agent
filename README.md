# DeepReason Learning Agent

面向计算机基础知识的本地学习助手。基于 [DeepReason Agents Framework](https://github.com/redmaplewww/DeepReason-Agents-Framework) 的 Python 运行核心，围绕多角色任务路由、证据交付、答案发布控制、会话一致性与教学 Skill 更新进行改造。

提供终端连续问答、概念解释与条件比较的实验流程；回答使用本地课程资料，资料不足时明确止答。当前聚焦树与哈希等小范围知识，核心工程机制已接通，真实问答质量仍在收尾验收。

## 核心机制

| 机制 | 当前实现 |
| --- | --- |
| 多角色工作流 | Coordinator 判断任务与风险，Reviewer 复核且只升级审查强度；明确的双主体比较采用两侧检索与证据汇合的有限计划，检查依赖、步数和交付条件 |
| 证据与发布控制 | 本地检索结合 BM25、词项相似度和共现扩展；Gate 检查证据资格，生成草稿再经过最终审查，并核对引用 ID、源哈希、原文摘录和问题维度后发布 |
| 会话与笔记可靠性 | 按线程保存近期历史；跨进程锁、获锁重载和快照替换保护会话提交；明确笔记写入使用 SQLite 操作回执与版本检查，支持重复提交核对 |
| 受控 Skill 更新 | 从明确反馈生成固定教学规则候选，经过触发案例检查、来源与版本绑定及人工审批后加载，支持回退 |

```text
问题与本线程历史
  → 路由与复核
  → 有限计划与本地检索
  → 证据审计与 Gate
  → Worker 生成草稿
  → 最终审查与引用核验
  → 发布结果并保存会话
```

Gate 阻断或资料不足时跳过 Worker；审查失败时扣留草稿。角色当前按流程串行执行。

## 快速开始

需要 Python 3.11 或更新版本。下面以 Windows PowerShell 和 Python 3.12 为例，在仓库根目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 无需模型密钥的演示

```powershell
.\.venv\Scripts\python.exe scripts\learning_mvp_demo.py
```

演示会展示六道代表题，并实际执行会话重启恢复、笔记重复提交，以及 Skill 提出、批准和回退。模型回答与审查由固定脚本提供，工作流、检索和存储实际执行。每次使用独立结果目录，不改现有学习会话。

### 使用千问连续问答

先在本机环境变量中配置 `DEEPREASON_QWEN_API_KEY` 或 `DASHSCOPE_API_KEY`，再运行：

```powershell
$env:DEEPREASON_QWEN_MODEL='qwen-max'
.\.venv\Scripts\python.exe run_learning.py
```

例如可以提问：

- 二叉树是什么？
- 什么是哈希冲突？
- 哈希表和二叉搜索树有什么区别？
- 哈希表一定比平衡二叉搜索树快吗？比较精确查找和范围查询。

输入 `/usage` 查看本地持久化请求计数，输入 `/exit` 退出。密钥仅在本机使用；程序不会自动读取 `.env` 文件。实际问答需要模型账户有可用额度，正常生成通常包含四次角色请求。

学习笔记可以通过 `run_learning.py --notes` 和 `--save-note` 等明确命令操作，完整参数见 `run_learning.py --help`；保存需要操作 ID 和当前版本，普通提问不会自动保存为笔记或画像。

## 验证

```powershell
# 有限终态验收：正常发布、资料不足、危险动作、坏路由与坏交付
.\.venv\Scripts\python.exe scripts\verify_learning_paths.py
```

离线验收使用固定模型回执检查正常发布与失败拦截，不能代替真实模型的内容质量验收。测试方法和路径覆盖口径见[测试说明](docs/MVP_TEST_REPORT.md)；其中的结果应按报告所标版本与日期理解。

## 当前边界

- 使用小型本地课程语料，跨主题问题需要补充有出处的资料。
- 引用存在不等于整条结论都有充分支持；证据外扩展与最终审查的历史条件传递仍在收尾范围内。
- 当前面向本地单用户，线程隔离不等于登录用户认证；笔记保障只覆盖已接入的明确写动作。
- Skill 是一条固定教学规则的受控更新实验，教学效果尚待对照验证；不宣称自主进化或整体性能提升。

## 来源与改动归属

基础编排、Workflow Spec、检索组件和 SessionStore 复用 DeepReason；学习场景、有限计划、交付检查、发布保护、会话与笔记适配、Skill 状态控制及评测由本项目在 AI 协助下实现和验证。逐项说明见[改动归属](workbench/PROVENANCE.md)。

上游版本、复用范围，以及 OpenDSA 教材资料的来源与许可统一见[来源说明](UPSTREAM.md)。保留随附的第三方许可文本。
