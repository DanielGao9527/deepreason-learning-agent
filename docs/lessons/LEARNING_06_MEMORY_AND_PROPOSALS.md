# 第六课：会话、长期记忆、证据与“自进化”各存什么

更新：2026-09-25。依据固定上游 `memory.py`、`sessions.py`、`evidence.py`、`evolution.py`、`multiagent.py` 的实际读写代码；`scripts/trace_memory_boundaries.py` 用临时目录直接调用组件，输出 `artifacts/analysis/memory_boundaries.json`。无模型调用或网络请求。组件实验不等于完整编排器端到端验证。

## 四种东西不是四个名字相近的数据库

| 信息 | 当前放在哪里 | 何时进入提示或后续任务 | 本轮写入规则 |
| --- | --- | --- | --- |
| 最近对话 | `ShortTermConversationMemory` 内存窗口；可选 `SessionStore` 的 `snapshot.json` | 按 thread ID 载入，默认最多保留 8 轮，提示默认用最近 6 轮 | 一次编排结束后追加问答并保存快照；会话快照不是工作流任意步骤的检查点 |
| 长期事实/偏好 | `memory/<partition>.jsonl`，例如 `user`、`project` | 编排器从配置分区逐个读取，再取末尾若干条，默认 12 条；没有按当前问题做语义重排 | 显式“请记住…”候选产生后，记录用户请求证据，经 `write_memory` 门禁写入 |
| 检索证据 | `evidence/ledger.jsonl`，保存来源、位置、摘要、哈希、证据 ID | 工作流按任务取证，门禁按资格和数量使用；不是用户偏好存储 | 检索或显式记忆请求时产生可追溯记录；记录存在不等于真实性已核验 |
| 经验/资料沉淀提案 | `evolution/proposals/*.json` 或 `evidence/consolidation-proposals/*.json` | 当前不自动变成已生效 Skill 或公共知识 | 调用方给证据、理由和建议后生成 `proposed` 文件；目标内容保持不变 |

Hermes 的热/温/冷可帮助理解**加载时机**，但不要硬映射为这四个文件种类：一条长期偏好被放进当前提示后，当前轮它也是“热”的。更值得面试讲的是作用域、写入权、失效和冲突处理。

## 离线实验具体证明什么

短期窗口限制为 2 轮，依次加入 3 轮，只剩第 2、3 轮；把它们保存到 `SessionStore` 后可以读回 4 条 user/assistant 消息。源码中的编排器用 thread ID 从快照恢复近期上下文；但这不意味着一次任务停在 `gate` 后可从该节点继续。

长期记忆在本实验中配置为中风险至少 1 条证据、`write_memory` 需审批：无证据返回 `interrupt`；有证据但无 `approved_by` 也 `interrupt`；两者都有才 `allow`。这只是字段检查，`approved_by="human"` 并非经过独立身份认证。相同 `user/report_style` 连续写 `brief` 与 `detailed` 后有 **2 条** JSONL 记录，`read(partition,key)` 返回后者；编排器的 `_load_long_term_memories` 却是按分区读全量再切末尾，所以旧值仍可能进入提示。它没有 `supersedes`、有效期或“用户已撤回”状态。实验故意复用同一证据写相反值，是为了暴露门禁未检查语义冲突，不能把这个写法当作正确业务流程。

显式记忆提取也基于关键词：`请记住我的回复风格是简短` 进入 `user` 候选；`请记住这篇论文的观点` 进入 `knowledge` 候选，后者不能直接写长期记忆。反例是 `请记住我的报告风格是简短`，其中“报告”命中知识库词表，同样被判为 `knowledge`。这说明现有分流会误拦个人偏好，不能声称已经有完整画像分类。

`SelfEvolutionEngine.propose_skill_update` 在本实验获得一条 ledger 证据后写出带 `evidence_ids` 的 `proposed` JSON；原 `SKILL.md` 字节不变。工作流的证据沉淀也只在 Gate 允许、有合格外部证据且置信度达到条件时生成提案，并不直接更新知识库。固定上游默认编排链没有自动完成“失败发现 → 技能修改 → 案例复跑 → 激活/回退”的闭环。因此目前只能称为**有证据的候选提案机制**。

## 如果我们要增强，先选一个真正的读写问题

首选问题是“用户纠正偏好后，旧值是否还影响新任务”。最小方案可以把长期记录增加 `subject_id`、`scope`、`source_event_id`、`status`、`supersedes` 和有效期，构建按用户、作用域与状态查询的**当前事实视图**，再把它注入提示。临时任务覆盖长期偏好，但不直接改写长期记录。用 A 用户/ B 用户、一次纠正、一次撤回、一次仅本任务覆盖四类案例检验。当前上游 `user.jsonl` 没有自动按用户主体隔离；仅凭 partition 名称不能宣称多用户画像隔离已完成。

经验提案应绑定具体失败轨迹和前提条件，再拿成功案例与反例复跑。只有候选通过验证并经过明确采纳，才进入被加载的 Skill 版本；保留旧版本才能回退。否则“生成一个 JSON 提案”只是待审资料，不是性能已提升的自学习算法。这是设计方向，**本轮未实现、未测量改进率**。

复现：在项目目录运行 `.\.venv\Scripts\python.exe scripts\trace_memory_boundaries.py`。所有模拟会话、记忆和提案都写在一次性临时目录里；只有不含个人数据的结构化结果写入 `artifacts/analysis`。
