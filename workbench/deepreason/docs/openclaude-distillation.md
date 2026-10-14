# OpenClaude 蒸馏映射

这份文档记录当前模板如何借鉴 OpenClaude 的架构经验，同时避免直接复制它的源码、目录形态和历史包袱。

## 来源边界

本地拉取的参考仓库位于 `openclaude/`，只用于架构研究。

OpenClaude 的许可证声明中提到，该仓库包含从 Claude Code 派生而来的代码。因此，本模板不应把 OpenClaude 当作源码依赖，也不应直接搬运其核心实现。更稳妥的做法是：学习它的能力边界、接口设计和运行时分层，然后用当前模板自己的代码重新实现一套干净、轻量、可维护的 Agent 框架。

## 进入核心的能力

以下能力决定了一个 Agent 框架是否完整，应该保留在轻量核心中：

- 无 UI 的 Agent 循环：模型响应、工具调用、工具执行结果、后续模型调用。
- 统一工具协议：工具名称、描述、输入 schema、执行函数、审批元数据。
- 风险动作前的权限闸：命令、文件写入、记忆写入、外部调用等动作必须先过闸。
- 工具步数上限：防止模型陷入无限工具调用循环。
- 稳定事件流：CLI、Web、测试、未来 SDK 都可以复用同一套运行事件。
- 会话消息结构：后续可以持久化、回放、恢复或审计。

当前第一版核心实现位于 `src/reasoning_agent_template/runtime.py` 中的 `AgentRuntime`。

## 插件化的能力

这些能力有价值，但不应该默认压进 starter template 的核心，否则模板会迅速变重：

- MCP 传输、鉴权和资源读取。
- 除最小 OpenAI-compatible 接口之外的复杂供应商适配。
- Web Search / Web Fetch 的多供应商实现。
- IDE 集成，例如 VS Code 插件。
- 后台任务、远程控制和桥接服务。
- 复杂终端 UI 或浏览器 UI 渲染层。
- 高级上下文压缩策略。

这些能力应该在项目确实需要时，再通过小接口逐步接入。

## 插件是否能分级加载、按需加载

结论：可以实现，而且必须这样实现。否则“插件化”只是把代码换了目录，本质上仍然会把模板拖重。

分级加载建议分成四层：

| 层级 | 加载时机 | 适合能力 | 目标 |
| --- | --- | --- | --- |
| L0 核心常驻 | 进程启动时 | `AgentRuntime`、`RuntimeTool`、`GatePolicy`、事件流、基础消息结构 | 保证最小 Agent 永远可运行 |
| L1 清单加载 | 启动时只读 manifest | 插件名称、描述、触发词、工具 schema 摘要、权限声明 | 让模型和 UI 知道“有什么能力”，但不导入重依赖 |
| L2 会话激活 | 某次会话需要时 | 供应商适配、基础工具包、RAG、记忆、简单 Web Fetch | 只为当前会话装配需要的工具和配置 |
| L3 调用时加载 | 工具第一次被调用时 | MCP 连接、浏览器控制、IDE 桥接、复杂搜索供应商、后台 worker | 避免启动成本、鉴权成本和长连接常驻 |

实现上需要一个 `PluginManifest` 和一个 `PluginLoader`：

- `PluginManifest` 只包含轻量元数据：`name`、`description`、`capabilities`、`triggers`、`tools`、`permissions`、`load_level`、`entrypoint`。
- `PluginLoader.discover()` 只扫描 manifest，不导入插件代码。
- `PluginLoader.activate(capability)` 在会话需要某类能力时导入插件入口。
- `PluginLoader.resolve_tool(tool_name)` 在工具真正被调用时懒加载工具实现。
- 插件入口必须返回标准 `RuntimeTool`、provider client 或 resource adapter，不能反向依赖 CLI/Web UI。

当前模板已经落地第一版插件基座：`src/reasoning_agent_template/plugins.py` 中的 `PluginManifest`、`PluginToolSpec` 和 `PluginLoader`。这一版先覆盖工具插件路径：manifest 可以提前暴露工具 schema、风险级别和权限声明，`PluginLoader.tool_proxies()` 生成给 runtime 使用的代理工具；真实插件实现只会在 `activate()` 或工具首次执行时导入。测试覆盖了 `discover()` 不导入插件、工具首次调用才导入实现、危险工具在实现导入前就被 `GatePolicy` 打断。

真正能按需加载的关键约束：

- 工具 schema 和工具实现要分离。schema 可以提前暴露给模型，实现可以等调用时再导入。
- provider 配置和 provider SDK 要分离。读取配置不应导入所有供应商 SDK。
- MCP server 配置和 MCP 连接要分离。启动时只知道有哪些 server，第一次使用相关工具时才连接。
- UI 展示和 runtime 执行要分离。Web/CLI 只订阅事件，不让插件依赖具体 UI。
- 权限声明必须早于执行加载。即使插件实现尚未导入，它需要的权限也必须先能被 `GatePolicy` 看见。

哪些能力适合按需加载：

- MCP：适合 L1 清单 + L3 调用时连接。MCP server 数量多、启动慢、鉴权复杂，绝不能默认全连。
- Web Search / Web Fetch：适合 L2 或 L3。默认只保留一个轻量 HTTP fetch；Firecrawl、Tavily、Brave、Bing 等作为按需 provider。
- 多供应商模型适配：适合 L1 清单 + L2 会话激活。会话选中 provider 后只导入对应适配器。
- IDE 集成：适合 L3。只有用户启用 IDE 桥接或工具调用需要 IDE 上下文时才加载。
- 后台任务：适合 L2/L3。只有出现长任务、monitor、cron、background agent 时才启动 worker。
- 高级上下文压缩：适合 L2。默认保留简单裁剪或摘要接口，复杂压缩策略按会话配置启用。

哪些能力不适合按需加载：

- 权限闸不能懒加载。否则工具执行前无法做稳定安全判断。
- 事件流不能懒加载。否则 CLI、Web、测试和审计无法统一观察 runtime。
- 基础工具协议不能懒加载。所有插件都要依赖这个协议。
- 配置解析和 manifest 扫描不能懒加载。否则系统不知道有哪些可用能力。

因此，插件化的判断标准不是“放在 plugins 目录”，而是：

1. 启动时是否只扫描 manifest。
2. 未启用插件时是否不导入重依赖。
3. 未调用工具时是否不建立外部连接。
4. 插件失败是否不影响核心 runtime 启动。
5. 权限声明是否能在插件执行前被审计。

只要按这个边界设计，分级加载和按需加载是可以真实落地的。

## 保留但分层实现的能力

你明确要求保留的两类能力：远程桥接/后台会话管理、复杂终端 UI。它们不再归入“明确剥离”，但也不能直接塞进 L0 核心。正确做法是保留能力目标，按阶段实现。

### 远程桥接、后台 daemon 和产品级会话管理

包括 remote control、bridge API、远程 worker、后台 session 管理、attach/logs/kill 产品命令、跨设备会话等。

保留原因：

- 长任务、异步 agent、远程执行、跨端接管都是完整 Agent 平台的重要能力。
- 后续如果要做真正可生产使用的 Agent 工作台，必须有会话生命周期、日志、恢复和远程控制。
- OpenClaude 在这块的价值不只是“后台命令”，而是把长任务变成可观察、可恢复、可管理的运行对象。

分层实现方式：

- L0 核心只保留 session message 结构、事件流和 session id。
- 第一阶段实现本地 transcript、resume、fork，为后台会话打基础。
- 第二阶段实现本地 background session：启动、状态、日志、停止，不引入远程鉴权。
- 第三阶段实现 attach/logs/kill 这类产品命令。
- 第四阶段再做 remote bridge：鉴权、远程 worker、跨设备会话和安全边界。

边界要求：

- 后台任务不能绕过 `GatePolicy`。
- 远程 worker 不能直接获得比本地 runtime 更高的权限。
- 日志必须结构化，至少包含 session id、run id、事件、工具调用和错误。
- bridge API 必须是插件或外层服务，不能反向污染 `AgentRuntime`。

### 复杂终端 UI 和 React/Ink 交互层

包括大量 terminal component、权限弹窗、选择器、状态栏、虚拟消息列表、diff UI、OAuth UI 等。

保留原因：

- 完整 Agent 产品确实需要高质量交互，尤其是权限审批、diff 审阅、工具进度、模型切换和会话恢复。
- 终端 UI 是高频开发者入口，不能只留下最小文本输出。
- 但 UI 只能是 presentation layer，不能和工具执行、权限判断、模型循环混在一起。

分层实现方式：

- L0 runtime 只产出结构化事件，不产出 UI 组件。
- CLI 第一阶段使用最小文本渲染，确保调试和自动化可靠。
- Web debug console 订阅同一事件流，作为结构化观察面。
- 复杂 TUI/React/Ink 放在独立 UI package 或插件层。
- 权限弹窗、diff UI、选择器都消费 runtime event 和 permission request，不直接调用工具内部实现。

边界要求：

- UI 不能决定权限，只能展示 `GatePolicy` 的请求并收集用户选择。
- UI 不能持有核心状态源，状态源应来自 session store 和 runtime events。
- UI 失败不能导致 agent runtime 崩溃；最多降级到文本模式。
- UI 组件不能被 provider、tool、MCP 插件反向依赖。

## 明确剥离的部分

以下内容不进入蒸馏后的通用模板。剥离不是因为它们没有价值，而是因为它们属于 OpenClaude 作为完整产品的外围重量，不适合作为通用 Agent 开发模板的默认负担。

### 项目运营资产

包括赞助商展示、社区链接、Discord/X 宣传、Star History、Code of Conduct、Security Policy、Release Please 配置、PR 模板和大量 GitHub Actions。

剥离原因：

- 它们服务的是 OpenClaude 项目自身的社区运营，不服务模板的 Agent 能力。
- 新项目会有自己的组织、发布节奏、安全政策和贡献规范。
- 默认携带这些内容会制造品牌和维护噪音。

替代方式：

- 模板只保留最小 `README`、架构文档、测试命令和配置说明。
- 当模板被实例化为具体项目时，再由项目生成自己的贡献、发布和安全文档。

### 增长实验、遥测和内部开关

包括 GrowthBook gate、实验性 feature flag、遥测字段、统计埋点、内部诊断事件、产品增长相关逻辑。

剥离原因：

- 这些代码会污染核心执行路径，让 runtime 难以理解和测试。
- 大量实验开关会造成“同一份代码多种行为”，不利于模板学习和二次开发。
- 通用模板不应默认采集遥测，也不应绑定任何增长平台。

替代方式：

- 核心只保留本地事件流 `events`。
- 如需观测，可通过插件把事件流转发到日志、OpenTelemetry 或自定义监控系统。
- feature flag 只保留项目级配置，不保留上游产品实验矩阵。

### 庞大供应商矩阵

包括 OpenClaude 中大量 provider 的专用分支、环境变量兼容层、OAuth 细节、模型别名、额度查询、错误分类和 provider-specific shim。

剥离原因：

- 供应商矩阵是重量增长最快的部分。
- 大量 provider 兼容逻辑会挤压 Agent 框架本身的清晰度。
- 模板用户通常只需要先接入一到两个模型供应商。

替代方式：

- 核心只定义 provider-neutral 接口。
- 默认实现 DeepSeek/OpenAI-compatible 这一类最小路径。
- Anthropic、Gemini、Ollama、Azure、Bedrock、GitHub Models 等作为 provider 插件逐步加入。

### VS Code 扩展和 IDE 产品层

包括 VS Code extension、控制面板、编辑器内聊天、主题支持、终端启动注入、IDE 专用 MCP server。

剥离原因：

- IDE 集成是产品体验层，不是 Agent runtime 核心。
- 它依赖具体编辑器 API，天然会把模板绑到某个宿主环境。
- 初始模板应先保证 CLI/Web/API 都能复用同一 runtime。

替代方式：

- 核心只保留事件流和工具协议。
- 以后通过 IDE 插件订阅 runtime 事件、调用 runtime API。
- IDE bridge 作为 L3 按需插件加载。

### 文档网站源码

包括完整官网、营销页面、站点构建工具、静态资源、部署配置。

剥离原因：

- 文档网站服务的是上游项目的传播和安装引导。
- 对通用 Agent 模板来说，它会增加依赖、构建步骤和维护面积。
- 模板真正需要的是开发者能快速读懂架构和扩展点。

替代方式：

- 保留 `docs/` 下的 Markdown 文档。
- 如果具体项目需要网站，再用独立文档站插件或项目脚手架生成。

### Legacy helper runtime 和语言混杂层

包括与 starter path 无关的 Python helper、兼容旧路径的 shim、历史迁移脚本、旧格式转换逻辑。

剥离原因：

- 历史兼容层对上游项目必要，但对新模板是负担。
- 多语言 helper 会增加安装、测试和打包复杂度。
- 新模板应优先保持单一主语言和清晰边界。

替代方式：

- 当前模板以 Python 为主。
- 只有当某个插件确实需要 Node/浏览器/本地二进制时，再通过插件声明外部运行时需求。

## 当前模板映射

| OpenClaude 架构点 | 蒸馏后在本模板中的落点 |
| --- | --- |
| `query.ts` 工具循环 | `AgentRuntime.run()` |
| `Tool.ts` 工具协议 | `RuntimeTool` |
| permission context | `GatePolicy` + 工具审批元数据 |
| tool result messages | runtime `messages` 中的 `role: "tool"` |
| sub-agent step limits | runtime 核心里的 `max_tool_steps` |
| UI progress | runtime `events` |
| plugin discovery / lazy loading | `PluginManifest` + `PluginLoader` |
| provider adapters | 后续 provider 插件，挂到 `PluginLoader` |
| MCP tools/resources | 后续 MCP 插件，基于 `PluginLoader` 做 stdio transport 和工具发现 |
| session transcript | `SessionStore` 已支持 snapshot / load / fork，resume CLI/API 待补 |

## 下一步建设顺序

1. 增加供应商无关的模型接口，用来包装 DeepSeek 和其他 OpenAI-compatible Chat Completions API。
2. 增加一组最小内置工具：文件读取、文件写入、Shell、Grep、Web Fetch、Todo、Sub-agent。
3. 把 `AgentRuntime` 接入现有 `MultiAgentOrchestrator`，作为可选执行后端。
4. 补齐本地 transcript / resume 的 CLI 和 API 入口；`fork` 的底层语义已经由 `SessionStore` 提供。
5. 增加本地 background session：启动、状态、logs、kill。
6. 把 MCP 做成插件，第一版只实现 stdio transport 和工具发现，并复用 `PluginLoader` 的 manifest-first / lazy-load 机制。
