# 第二十五课：会话保护为什么必须覆盖整轮执行

更新：2026-10-15。范围是本地 `LearningAssistant` / `LearningOrchestrator` 问答入口；没有改固定上游、Fitness、通用 Runtime 或 Web 入口。课程代码由本项目与 AI 协作完成。

## 一个实际复现的问题

先创建两个指向同一工作区、同一 thread 的助手 A、B，使用同样的脚本模型和课程资料，依次完成三轮：A 问第一题，B 问第二题，A 问第三题。

改动前，三轮均返回成功，但最终快照只有第一、第三轮，**期望 3 轮，实际 2 轮，第二轮丢失**。不需要真正并发也能复现：上游 `_short_term_memory_for()` 只在进程内缓存不存在时读文件；A 第三次使用的仍是自己的第一轮缓存，覆盖了 B 已提交的第二轮。

所以，只在 `record_snapshot()` 写文件时加锁仍会丢数据：两边可能已经根据旧历史生成答案，写锁只决定谁最后覆盖谁。锁需要从读取历史之前持有到整轮保存之后；重新获得锁，也必须重新加载最新的已提交历史。

同样初态改动后：**期望 3 轮，实际 3 轮**；第三轮 Coordinator 的真实调用参数包含前两轮历史。另一个子进程提交第二轮后，原助手继续第三轮也保留三轮。这里只证明已测的会话顺序与提交行为，不是答案正确率或吞吐提升。

## 当前实现

| 边界 | 具体机制 | 代码位置（工作副本内） |
| --- | --- | --- |
| 一个实例一次执行 | 非阻塞实例锁；上游只有一个 `_active_run` 状态槽，因此同实例即使换 thread 也明确拒绝第二个请求 | `src/reasoning_agent_template/learning.py`：`LearningOrchestrator.run` |
| 多实例 / 多进程同会话 | 用实际 snapshot 路径的哈希作为稳定锁文件名；Windows 路径先按大小写规则归一。持有本地操作系统非阻塞文件锁，竞争者报 `LearningSessionBusyError`，不排队、不调用模型、不建立该轮失败轨迹 | `learning_sessions.py`：`session_execution_guard` |
| 旧缓存与未提交缓存 | 获锁后移除该 thread 内存缓存，让原加载器读取最新快照；无论本轮成功或异常，都清除该轮缓存 | `learning.py`：`LearningOrchestrator.run`；复用 `multiagent.py`：`_short_term_memory_for` |
| 完整快照提交 | 沿用上游 SessionSnapshot 格式和路径校验；先在目标目录写临时文件、flush/fsync，关闭后用 `os.replace` 替换；替换失败则保留旧快照并清理临时文件 | `learning_sessions.py`：`LearningSessionStore._write` |
| 用户可见失败 | 单次命令返回退出码 2 和等待提示；交互模式显示本轮忙碌，仍可继续输入 | `learning.py`：`main`、`interactive_session` |

Windows 使用标准库 `msvcrt.locking(..., LK_NBLCK, 1)`，锁定从偏移 0 开始的一字节区域；这个区域允许超出文件末尾，所以锁文件可以保持空文件。非阻塞与区域语义见 [Python msvcrt 文档](https://docs.python.org/3/library/msvcrt.html)。代码也提供 [fcntl.flock](https://docs.python.org/3/library/fcntl.html) 分支，但本次只在 Windows 实测。文件替换使用 [os.replace](https://docs.python.org/3/library/os.html#os.replace)；没有把 flush/fsync 和一次替换解释成所有存储介质上的断电事务保证。

锁文件不删除。它是稳定的竞争目标，存在不代表当前有人持锁；关闭句柄才释放锁。删除并重建锁文件可能使不同进程锁住不同文件。本次强制终止正在 Worker 阶段的子进程，未手动清理锁文件，下一请求仍可正常获得锁并完成。

原来的 thread 归一化规则仍保留：例如 `learner.a` 实际使用 `learner-a`；两种写法必须竞争同一把锁。thread 只是本地命名空间，没有认证含义。Windows 的 `LEARNER` / `learner` 同路径竞争也已测。

## 验证结果与覆盖边界

针对性 **14/14**，完整工作副本 **220/220**（128.796 秒），原九例学习入口验收 **9/9**。第一次针对性运行有两处测试读取了不存在的 `short_term_before` 输出字段；改为核对实际 Coordinator 调用参数后全过，没有修改产品输出来迎合测试。完整回归后的示例 Ledger 已恢复至固定上游 SHA-256。

| 正常或故障案例 | 实际结果 |
| --- | --- |
| A→B→A 顺序执行 | 改前最终 2/3 轮；改后 3/3 轮，且第三轮路由收到前两轮 |
| 一个实例的 Worker 挂起，另一个 thread 进入 | 第二请求 `assistant_busy`；活动状态仍属于第一轮；没有额外模型调用 |
| 两个实例同 thread，第一轮停在 Worker | 第二请求 `session_busy`，脚本模型调用 0；第一轮完成后第二轮可继续并保留两轮 |
| 子进程停在 Worker，另一个进程提问 | 竞争请求在模型初始化前被拒；强制终止持锁子进程后，无需删文件即可完成下一轮 |
| 另一个子进程提交后，旧实例继续 | 旧实例重新加载新历史，保留全部三轮 |
| 快照替换前注入磁盘错误 | 旧文件字节不变；临时文件清理；失败轮不进入下一轮的路由上下文 |
| 模型 403、非法路径 ID、损坏 JSON | 不保存新的会话；锁释放；损坏历史不会被自动当空历史覆盖 |
| thread 别名 / Windows 大小写 | 对应同一个快照时竞争同一锁；不同 thread 和工作区的锁互不冲突 |
| 锁目录/句柄 IO 错误 | 保持原 IO 错误，不误报为普通忙碌 |
| 单次 CLI / 交互模式遇到忙碌 | 友好返回；不初始化千问；交互仍可退出 |

这些是 14 项故障/回归测试的覆盖，不能称系统路径覆盖率。九例工作流验收依然只观察到 14 条声明边中的 9 条和一种完整节点序列；本次没有新增工作流分支。

从仓库根目录运行：

```powershell
Set-Location workbench\deepreason
$env:PYTHONPATH='src'
..\..\.venv\Scripts\python.exe -m unittest tests.test_learning_sessions -v
```

原始对照摘要在本机 `artifacts/analysis/learning_session_baseline.json` 和 `learning_session_after.json`，完整测试输出在 `learning_session_full_tests.txt`；运行产物不提交到 Git。

## 真实模型实验的独立记录

本次也显式启动了上一课现成的 `--qwen --max-calls 32` 配对入口。第一条 route 请求在约 **464.07 ms** 返回 **HTTP 403**，`retryable=false`；实验 `skill_a884c2cd9f41` 为 `aborted/non_retryable_backend_failure`，没有第二次请求，也没有生成评分包。本机仓库预占 **14→15/100**。

本次脱敏报告没有提供方具体错误码，不能仅凭 403 断言仍是历史 `AllocationQuota.FreeTierOnly`。没有真实回答、usage、质量或 Skill 收益数据；完整记录在本机 `artifacts/experiments/skill_a884c2cd9f41/manifest.json`。此后实现和测试全部使用脚本模型，真实千问请求为 0。

## 尚未覆盖与下一入口

- 只保护通过学习入口、同一台机器本地文件系统的合作调用；原上游 Web、通用 CLI、手工编辑、直接调用 SessionStore 的 fork/delete 没有自动加入此锁。没有多机器/网络盘验证。
- 忙碌立即拒绝，没有队列、公平调度或自动重试。不同 thread 的锁独立，但共享 Ledger、Spec、Skill 等资源没有整体并发事务，不能写成完整并行多 Agent 平台。
- 进程在保存前被终止，没有该轮快照，但此前模型调用和 Ledger 记账可能已发生；不会自动续跑。保存成功后响应丢失仍可能导致用户重复提问，问答没有持久请求幂等回执；笔记的操作 ID 机制是另一条已经实现的边界。
- 替换前故障保留旧历史，不等于响应、会话、Ledger、Skill 之间的跨资源事务，也没有验证断电或磁盘损坏恢复。

面试可据实写：**“为学习问答增加本地跨进程会话执行互斥，获锁后重载已提交上下文，以临时快照替换和失败缓存清理防止交错覆盖；复现并修复 A→B→A 三轮丢失一轮的问题，覆盖 Worker 期间竞争、进程退出和提交失败等故障。”** 上游贡献是会话格式、存取与滚动窗口；本项目新增执行互斥、重载接线和提交边界。

下一步仍需独立复核真实答案与题目；真实服务恢复后先做一题低调用烟测，再运行有界配对实验。额度不可用时，下一工程入口是 guided 路径最终答复缺少同级审查的边界核对，先复现一个实际反例，再决定最小修改；不再扩展通用评测平台。
