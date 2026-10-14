# 来源与改动归属

记录日期：2026-09-25。

- 仓库：[redmaplewww/DeepReason-Agents-Framework](https://github.com/redmaplewww/DeepReason-Agents-Framework)
- 固定提交：`e98313d661527c3aa6677eec08a3b54b4ab88a33`
- [该提交的 runtime.py](https://github.com/redmaplewww/DeepReason-Agents-Framework/blob/e98313d661527c3aa6677eec08a3b54b4ab88a33/src/reasoning_agent_template/runtime.py)
- 用户于本轮说明，已通过其他渠道与作者联系并确认 MIT 授权。此次读取的仓库快照未找到 LICENSE 文件；这里记录用户提供的授权信息，不声称已从仓库取得许可证文本。

## S0 原样复用

以下为 S0 抽取时原样核对的文件与哈希。路径在本项目与上游相同；S1 已修改 runtime.py，表内该项保留原始上游哈希用于比较，其余五项未改。

| 文件 | Git blob SHA-1 |
| --- | --- |
| `src/reasoning_agent_template/runtime.py` | `ba4498515ab7017784f9e169e8d5d439ad83c4ba` |
| `src/reasoning_agent_template/config.py` | `338156049b6ac384d464a61b85a10d29096fbbd7` |
| `src/reasoning_agent_template/gates.py` | `d077c5a0edb7bc6eecc40e4f9548941c2743d66c` |
| `src/reasoning_agent_template/models.py` | `6d57827da47dd0cfd37fb418a2095b0906946b9a` |
| `src/reasoning_agent_template/sessions.py` | `af319be99298e3dba99089fc659170003205c0e3` |
| `tests/test_agent_runtime.py` | `4979ac6efdc0dc5417c9a7c3b8fd9db28176fc84` |

S0 当时仅抽取上述文件，没有复制密钥或完整平台。保留原包名便于对应源码。后来为交接获取的完整快照见下方；2026-09-25 完整上游 118 项离线测试通过，真实模型和 CLI/Web 未联调。

## 完整源码交接

2026-09-25 已在本机获取 `references/deepreason-full`，检出固定提交，保留全部 142 个受版本管理文件：原代码、文档、配置、前端、测试和作者公开示例。来源与逐文件 SHA-256 见 `references/UPSTREAM_SNAPSHOT.json`。完整原样快照不随本公开仓库发布；可从上方固定提交重新获取。公开仓库中的 `workbench/deepreason/` 是已修改的工作副本。

便携包保留完整受版本管理快照，不含 .git 历史。作者 evidence/knowledge 示例不是用户个人记录或本地新实验。lab 新增和修改仍位于 src/tests，完整上游存在不表示这些模块已接入 lab。

## S0 本地新增

- 两个包的初始化文件、离线演示模块、启动与测试入口。
- 合成资料、消息驱动的脚本模型、实际执行的只读工具。
- 两项整体验证、学习文档和接续状态。
- 中文终端输出修正仅作用于本地启动入口。

这些由助手在用户授权下生成与验证；用户的理解和设计讨论仍要逐模块进行。初始工具循环主体来自上游，不能写成“本人从零设计实现”。

## 后续变更记录方式

开始精简或重构后，在 STATUS 记录改了哪些模块、保留哪些行为、为何需要改及验证结果。需要追溯原始代码时使用上述固定提交，不随最新上游静默漂移。简历归属以最终真实代码和实验为准。

## S1 接入改动

- 新增 `qwen.py`：使用 OpenAI SDK 连接阿里云，仅转换内部协议、检查响应完整性、记录调用次数和供应商返回的用量。
- 新增 `qwen_demo.py`、`run_qwen.py`：有限次数的真实调用入口、缺配置状态、必要证据核对；继续使用原工具与合成资料。
- 修改上游 `runtime.py`：新增 `ModelCallError`，在模型调用处捕获这类已分类异常，经既有 `_result()` 保存失败状态。工具循环其余路径保留。这个改动属于本地接入所需的失败处理，不宣称修复整个上游平台。
- 新增 SDK 协议测试，网络使用 `httpx.MockTransport`，不能当作千问真实调用成功。
- 网络处理使用现成 SDK，不新增通用模型框架；未删除或重写 config/models 等模块。
