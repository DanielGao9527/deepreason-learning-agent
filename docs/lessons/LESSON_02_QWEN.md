# 第二课：复用运行核心，把真实千问接进来

最新说明：用户已纠正教学重点，本课仅保留为接入参考。主线转到 CORE_MECHANISMS；无需完成本课或新建 Key 才能继续。已有有效阿里云 Key 可以使用，“独立配置”不要求创建另一把 Key。

## 这次做什么

第一课的模拟模型按固定规则安排动作；这次替换为千问适配器，保留同一个 DeepReason 工具循环与两项只读工具。资料仍是合成示例，避免同时引入网络搜索和资料质量两个变量。

用户已表示第一课概念理解，可以继续；也提醒不要在三天里重写通用框架。本轮采用 SDK 与上游 Runtime，只增加必要接线和失败处理。没有新建 Agent 框架，也不为凑层数拆模块。

## 复用与新增

| 部分 | 处理方式 |
| --- | --- |
| 工具循环、查找工具、执行函数、回填消息、步数限制、快照 | 继续复用 DeepReason |
| HTTP、认证头、连接管理、供应商响应对象 | 使用现成 OpenAI SDK 2.54.0，连接阿里云兼容接口 |
| 内部消息与供应商格式转换 | 新增 `src/deepreason_lab/qwen.py`，实现原有 `complete()` 接口 |
| 模型失败记录 | 原 Runtime 增加 `ModelCallError` 的定向捕获，记录 `failed` 和快照 |
| 启动与最小产物检查 | `qwen_demo.py`：检查真实读取了两份资料、答案带两个来源标记 |

使用 OpenAI SDK 是阿里云官方兼容接入方式之一，不代表模型请求发给 OpenAI。模型地址和密钥均对应阿里云。

## 只需要先理解一个转换

Runtime 内部的一张请求单：

```json
{"id":"call-a","name":"read_source","arguments":{"source_id":"demo-a"}}
```

回传给千问时，接口要求这样的结构：

```json
{"id":"call-a","type":"function","function":{"name":"read_source","arguments":"{\"source_id\":\"demo-a\"}"}}
```

内层参数从字典变成 JSON 字符串。适配器负责来回转换；执行函数、预算和状态仍由原 Runtime 管。这种接口对接属于实际接入工作，不需要再写一套工具循环。

## 型号与启动

按用户“与 Fitness 相同”的选择，对齐 Fitness 当前仓库的 `config.py` 与配置示例：

- 模型：`qwen3.7-plus`。
- 地域：北京；兼容地址：`https://dashscope.aliyuncs.com/compatible-mode/v1`。
- 未读取 Fitness 密钥或部署环境覆盖值；以上是本地仓库明确配置。

模型与地址已有默认值，也可通过 `DEEPREASON_QWEN_MODEL`、`DEEPREASON_QWEN_BASE_URL` 环境变量覆盖。第一轮关闭思考，非流式；最多 4 次模型请求、4 次工具调用，每次输出上限 1024 token，网络超时 30 秒，SDK 自动重试为 0。这些限制不等同于固定人民币费用或严格的任务总时限。

在本项目目录检查配置，**不会调用模型**：

```powershell
.\.venv\Scripts\python.exe run_qwen.py
```

本地交互运行真实模型：

```powershell
.\.venv\Scripts\python.exe run_qwen.py --live --ask-key
```

终端会隐藏密钥输入，只供本次进程使用，不写入配置文件。无需把密钥发到聊天。也支持预先设置 `DEEPREASON_QWEN_API_KEY` 后用 `--live` 运行。`.env.example` 仅说明配置项，程序不会自动加载 `.env` 文件。

首次在其他机器安装环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

本机已安装。运行测试仍使用 `scripts/check.py`；HTTP 被测试替身接管，不请求阿里云。真实模型是否已经验证，以 STATUS 为准，测试通过不能替代真实调用。

## 为什么处理失败

当模型因为长度限制只生成半句话时，接口可能仍有文字，但不能把它当完整答案。本轮拒绝截断、部分响应、空回答、坏工具参数和不一致结束状态；超时与 HTTP 错误也会进入明确失败状态。记录稳定错误代码，不保存供应商原始错误正文或请求头。

如果模型直接写了一篇带引用的答案，却没有真正读取两份资料，外层必要证据检查会拦下，保存 `draft.md`；通过时才保存 `report.md`。这只核查“资料是否读过、引用标记是否存在”，不是完整事实正确性验证。报告语义仍需人工核对。

现在唯一改动的上游模块是 Runtime 的模型失败分支；其他四个上游依赖保持原样。未知编程错误不被统一吞掉，仍会暴露出来便于修复。

## 下一步观察真实轨迹

看千问用了几轮、有没有一次返回两项请求、是否真的看了两份材料、报告依据是否正确。如果真实调用暴露问题，先定位在格式转换、执行控制还是模型行为，再决定改哪一处。

跑通之后直接进入任务状态与恢复：沿用现有 SessionStore，把保存的状态接回执行路径。这一阶段不以重写配置系统为任务。

## 官方依据

- [阿里云 Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)：工具定义、消息回传、关闭思考示例。
- [Chat Completions 兼容接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)：参数、结束原因及区域地址；官方说明北京旧域名仍可使用。
- [文本生成说明](https://help.aliyun.com/zh/model-studio/text-generation)：部分响应行为。

核对日期：2026-09-24。使用固定 SDK 版本；后续改模型或接口时重新验证。
