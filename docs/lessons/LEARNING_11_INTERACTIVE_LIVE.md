# 第十一课：自己在终端提问，观察 Agent 怎样交付

更新：2026-09-25。此课对应可修改完整工作副本的学习助手，非固定上游已有产品。与第十课的脚本模型 JSON 不同，本课使用本机已配置的千问环境变量做过两道真实问题联调。

## 你现在怎样使用

在仓库根目录的 PowerShell 中：

```powershell
.\.venv\Scripts\python.exe run_learning.py
```

看到 `你>` 后直接输入问题，按回车。连续提问沿用 `default` 会话；关闭后重新启动仍读取该会话近期记录。输入 `/usage` 查看本机累计模型请求；输入 `/exit` 退出。用 `--thread my-study` 可以单独开一个会话，例如 `.\.venv\Scripts\python.exe run_learning.py --thread my-study`。单次提问可用 `.\.venv\Scripts\python.exe run_learning.py '什么是哈希冲突？'`。程序读取已有 `DASHSCOPE_API_KEY` 或 `DEEPREASON_QWEN_API_KEY`，不用在聊天、命令或文件里粘贴 Key。

建议先试三题：

1. `什么是哈希冲突？`：观察 guided、资料与 Worker 回答。
2. `哈希表一定比二叉搜索树快吗？如果需要范围查询，该怎么选？`：观察 deep 和独立产物评审。
3. `请解释 ZxqvPrime-99 的内部缓存协议。`：资料外问题应止答；路由与 Reviewer 仍会消耗模型请求。

目前只覆盖哈希、二叉搜索树和算法复杂度这几个主题；第三题是检验边界，不是知识库广度测试。你可以把资料放在 `workbench/deepreason/learning_mvp/knowledge/`，支持 `.md`、`.txt`、`.json`。新增资料前要检查来源和冲突，不能把模型生成的未核实答案直接当教材。

## 原始教材与来源

本地现在有三份项目撰写的中文提要和三份从 OpenDSA 官方 GitHub 固定提交下载的英文教材原文。原始 `.rst` 保存在 `learning_mvp/source/OpenDSA/`；`scripts/import_opendsa.py` 校验 SHA-256 后去除教材嵌入控件指令，生成 `knowledge/04` 至 `06` 三个可检索文本。固定提交、每篇文件哈希和链接在 `learning_mvp/SOURCE_MANIFEST.json`，MIT 许可原文在 `source/OpenDSA/MIT-license.txt`。这只是一个局部语料，不是完整计算机知识数据库或预建向量数据库。运行时调用上游 `LocalKnowledgeBase` 读取本地文件，按原有 BM25、轻量语义和图关系评分检索；没有下载或使用外部向量模型。

## 一次回答具体怎样产生

源码入口是 `run_learning.py`，业务接线在 `workbench/deepreason/src/reasoning_agent_template/learning.py`。Coordinator 先给难度和证据路线，Reviewer 复核；本项目强制用本地资料。随后上游工作流检索本地片段，证据审查和 Gate 判断能否继续。Gate 不放行或没有合格资料时跳过 Worker；放行后由 Worker 起草。严格题还多一次独立产物 Reviewer，审查不过就扣住草稿。终端显示的是最终交付、路线、门禁、来源和状态轨迹，而不是原始模型响应。近期会话由上游 `SessionStore` 保存在本地；本项目禁止把提问自动写成长期画像。

`guided` 不等于没有验证：它仍经过本地证据和 Gate，但最终答案只标记为 `released_gate_only`，没有语义逐句证明。`deep` 的 Reviewer 也只是另一轮模型判断，加上引用结构检查，不能当作可靠的事实证明。源链接表示检索到了相关材料，**不保证每句话都被该材料支持**。提问时留意可能的过度概括或不相关来源。

## 本次验证与目前边界

本机真实千问两次答题：

| 问题 | 路径/结果 | 请求数 | 人工检查 |
| --- | --- | ---: | --- |
| 什么是哈希冲突？ | guided / answered / Gate allow | 3 | 回答的定义、冲突无法普遍消除和示例基本正确；引用列表含其他主题片段，逐结论引用仍待改进 |
| 哈希表一定比二叉搜索树快吗？如果需要范围查询，该怎么选？ | deep / answered / Gate allow | 4 | 回答区分精确查找、范围查询、树是否平衡和极端情况；仅人工粗核，不是完整语义评测 |

累计 **7/100** 次真实请求；计数在 `learning_mvp/local_state/qwen_usage.sqlite3`，每次发送前预占，包括失败请求。`--usage` 只读。交互入口 `/usage`、`/exit` 的无模型烟测通过；新增交互会话单测、原有七项学习助手单测通过。完整工作副本回归结果以 `docs/STATUS.md` 最新记录为准。

尚未完成：更广的知识采集与离线检索评测、逐结论语义归因、学习者画像与冲突处理、长期记忆沉淀、Skill 候选/回滚、在线安全隔离、部署或用户研究。下一步先用你实际提的题收集“来源不相关、条件遗漏、错误止答”案例，再针对一个具体失败改检索或交付契约。
