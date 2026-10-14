# 第十九课：读可以重试，写必须核对结果

这是开发路径 C 的一个**具体学习动作**：查看某个 thread 的本地笔记，以及用户通过命令行明确确认保存一条笔记。它让上游独立的 Tool Runtime 真正执行这一读一写，同时验证重复提交、超时和竞争。学习问答的模型暂时不会自主调用这两个工具。

## 先看上游边界

上游 `runtime.py` 已有工具注册、名称白名单、参数 Schema、路径/动作 Gate、工具超时、最大步数与内存中的 `_idempotency_results`。这些适合做执行入口，但内存结果在新进程中消失；超时的 Python 线程可能仍继续写。于是“工具超时”不能简单判为失败并重试，否则第一次写入可能随后完成，第二次又写一遍。仅凭调用前后的自然语言也不能证明是哪次操作成功。

本项目新增 `learning_notes.py`：默认数据库在工作区 `local_state/learning_notes.sqlite3`，已被 Git 忽略。每条明确保存命令带 `thread_id`、`operation_id`、`body`、`expected_version`；数据库事务同时写笔记与回执，并对 `(thread_id, operation_id)` 设置唯一约束。相同操作 ID 和相同正文重放返回原笔记 ID；相同 ID 换正文直接冲突；同一 thread 的不同操作若持有旧版本，拒绝写入。版本只属于这一笔记表，不是整个问答 SessionStore 的版本控制。

为什么还要比较正文？如果工具在返回回执前超时，运行时按操作 ID 查询已提交记录。若只看 ID，模型或调用方把同一 ID 换成另一条正文后，旧回执会被误当成新写入成功。本项目的 `reconcile_save` 同时对照哈希与原始正文；不匹配时保持 `uncertain`，不报告成功。

## 执行顺序和失败语义

保存命令沿上游 `AgentRuntime`：工具名白名单 → `write_file` Gate 与固定数据库路径 → Schema 检查（包括拒绝多余字段）→ SQLite 事务。CLI 的 `--save-note` 是明确的本地用户动作，才传入 `approved_by=explicit-local-user`；问答模型的普通文字不会自动获批保存。只读 `list_learning_notes` 最多在超时后再试一次，写入 `save_learning_note` **不自动重试**。

写动作返回超时或未知异常时，运行时立刻查询持久回执：有匹配正文的回执，报告 `tool_result_reconciled`；没有则报告 `tool_outcome_uncertain`，提示按操作 ID 核对。即使当时查不到，已启动的线程仍可能稍后提交。因此 `uncertain` 不是“保证没写”，更不能换一个操作 ID 盲目重做。明确的参数错误、旧版本、同 ID 换正文则返回 `failed`。命令行现在可以 `--note-receipt` 核对回执，之后仍使用**同一操作 ID、同一正文**重试，事务保证只保留一条。

## 本机亲手实验

在仓库根目录 PowerShell 使用自己的测试 thread，全部命令都不会调用千问：

```powershell
.\.venv\Scripts\python.exe run_learning.py --notes --thread note-demo
.\.venv\Scripts\python.exe run_learning.py --save-note "复习哈希冲突" --thread note-demo --operation-id note-001 --expected-version 0
.\.venv\Scripts\python.exe run_learning.py --note-receipt note-001 --thread note-demo
.\.venv\Scripts\python.exe run_learning.py --save-note "复习哈希冲突" --thread note-demo --operation-id note-001 --expected-version 0
.\.venv\Scripts\python.exe run_learning.py --notes --thread note-demo
```

第一次保存预期 `created/version=1`；第二次同 ID 同正文预期 `replayed`，列表仍只有一条。若 thread 先前已经有笔记，先读出当前 `version`，换一个新的 `operation_id` 并把该版本填入 `--expected-version`。回执查询只表示这个 ID 有提交；针对超时后的重试，运行时还会比较正文。

## 已验证案例与代码归属

离线测试包括：无确认时 Gate `interrupt`、明确命令放行、参数多余字段与工作区外路径拒绝、同 ID 重启后只写一条、同 ID 换正文冲突、旧版本无部分写入、同 thread 两个竞争写只有一个提交、两个进程同 ID 只提交一条、写线程超时后回执晚到、写已提交却丢响应时回执恢复、只读重试一次而写不重试、CLI 不读取千问配置。还测试了“旧 ID 配不同正文 + 超时”的反例，不允许拿旧回执假报成功。

本课针对性测试 `tests/test_learning_notes.py` **17/17**；完整工作副本 **174/174**（见项目状态中的最终回归结果），学习工作流八例仍 **8/8**，真实千问调用 **0**。上游原有 `runtime.py` 是复用底座；新的笔记事务、回执匹配、CLI 接线、读写区别策略和故障实验是本项目与 AI 协作新增。`runtime.py` 的新字段与重试/核对分支是适配改动；上游其他写工具仍只有原本的内存去重，**不能统称所有工具都获得持久幂等**。

这个实验不是 MCP 接入，也没有让学习者画像或长期记忆自动写入。`thread_id` 只做本地命名空间，没有登录身份验证；并发版本控制只覆盖学习笔记数据库。写入发生后，无法用工具 Runtime 的超时取消底层线程；解决方式是持久幂等和回执核对。下一课应区分“明确保存的学习笔记”与可影响回答的确认事实、历史证据、Skill，不能把此笔记表直接命名为完整四层记忆。
