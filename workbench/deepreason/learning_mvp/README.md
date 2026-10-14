# Learning Reasoner MVP

这是一份独立学习工作区，运行代码仍是 `src/reasoning_agent_template/` 下的完整 DeepReason 工作副本。`knowledge/` 有四份带来源的中文提要及三篇从 OpenDSA 官方仓库固定提交导入的英文原文，主题覆盖哈希、二叉树、二叉搜索树与算法分析。原始文件、固定版本、许可和哈希见 `source/OpenDSA/`、`SOURCE_MANIFEST.json`、`CURATED_SOURCE_MANIFEST.json`。

从项目根目录直接进入连续提问：

```powershell
.\.venv\Scripts\python.exe run_learning.py
```

输入 `/usage` 查看调用次数，`/exit` 退出。建议先问“什么是哈希冲突？”；完整说明见项目根目录 `docs/lessons/LEARNING_11_INTERACTIVE_LIVE.md`。

从 `workbench/deepreason` 目录运行：

```powershell
$env:PYTHONPATH='src'
..\..\.venv\Scripts\python.exe -m reasoning_agent_template.learning --usage
..\..\.venv\Scripts\python.exe -m reasoning_agent_template.learning --thread my-study '什么是哈希冲突？'
```

第二条命令需要本机 `DEEPREASON_QWEN_API_KEY` 或 `DASHSCOPE_API_KEY`。默认模型是 `qwen3.7-plus`、北京兼容地址；可以用 `DEEPREASON_QWEN_MODEL` 与 `DEEPREASON_QWEN_BASE_URL` 覆盖。每次实际模型请求先占用本仓库共享的 100 次上限，`--usage` 只读计数。没有 Key 时明确退出，不会调用模型。

离线流程演示从项目根目录运行 `.venv/Scripts/python.exe scripts/learning_mvp_demo.py`；它使用脚本模型，不评价真实答案质量。课程解释与局限见项目根目录 `docs/lessons/LEARNING_10_LEARNING_ASSISTANT_MVP.md`、`docs/lessons/LEARNING_11_INTERACTIVE_LIVE.md`；最新实测状态见 `docs/PROJECT_STATUS.md`。目前只有近期会话恢复，没有长期学习者画像、Skill 自进化或完整课程库。
