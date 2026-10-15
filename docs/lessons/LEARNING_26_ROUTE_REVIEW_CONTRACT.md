# 第二十六课：Reviewer 失败不能算完成复核

更新：2026-10-15。对应现行开发路径 **S1.1**，仅修改完整工作副本中的学习入口；固定上游与 Fitness 未改。本课不调用真实模型。

## 实际失败及改前/改后

对“什么是哈希冲突？”固定脚本 Coordinator 与资料，只替换 Reviewer 回执：

| Reviewer 原文 | 改前 | 改后 |
| --- | --- | --- |
| `not valid json` | `not_available`，仍继续调用 Worker 并保存回答 | `route_review_failed/invalid_review_json` |
| `{}` | 补默认 `approve`，继续生成并保存 | `route_review_failed/invalid_review_status` |
| `{"review_status":"aprove","findings":[]}` | 拼错状态被归一化成 `approve`，继续生成并保存 | `route_review_failed/invalid_review_status` |

三个反例改前全部调用 `route → reviewer → worker`，改后只调用 `route → reviewer`，检索/Worker 未执行，没有该轮会话提交。原始摘要在本机 `artifacts/analysis/learning_route_review_before.json`、`learning_route_review_after.json`，不进 Git。它们是三种故障的行为对照，不是答案准确率。

问题发生在**归一化之前**：默认值可以用于展示或兼容字段，却不能把“缺少审批决定”转成“已经批准”。如果只检查归一化后的 `review_status`，空对象和拼错状态已经变成批准，无法辨别原始缺失。

## 实现及职责

复用上游 `_call_reviewer()` 的模型调用、计时、有限重试和只升级合并。在工作副本 `multiagent.py` 只增加 `_parse_route_review()` 可覆盖入口；通用调用仍保留原宽松解析。学习场景在 `learning.py` 覆盖这个入口，先检查原始回执，再进入上游合并。

- 只接受一个 JSON 对象，允许一个完整的 JSON 代码围栏；多个对象、额外散文、重复字段和非标准 NaN/Infinity 拒绝。
- `review_status` 必须明确为 `approve / escalate / revise`，`findings` 必须是非空字符串组成的数组；`approve` 要求数组为空，修改/升级要求至少一条发现。
- 可选路线字段必须符合已有枚举；来源、列表、查询和 confidence 检查类型。confidence 只接受 0–1 的整数/浮点数，拒绝布尔值、非有限数及超范围值；未知字段不静默接受。
- `escalate/revise` 如果没有使上游实际采用更严格路线，返回 `review_change_not_applied`。修改建议本身不等于运行时已消费修改；有效升级仍实际进入严格工作流。
- 格式失败抛受控 `LearningRouteReviewError`，不再次请求模型修复；模型传输失败仍复用已有策略：403 不重试，模拟 503 最多重试一次。

学习 Reviewer 提示同步明确上述契约。程序负责格式、取值及可执行的升级判断；模型仍负责判断任务是否需要升级，不能据此保证意图/风险分类永不出错。有效 `approve` 携带较弱字段，也不能降低 Coordinator 原本已设置的严格路线。

## 发布、会话和失败状态

此校验发生在 `route_review` 阶段、工作流开始之前。失败异常沿既有编排器异常路径记录脱敏终态：

```json
{
  "terminal_status": "route_review_failed",
  "reason_code": "invalid_review_status",
  "phase": "route_review",
  "session_saved": false
}
```

记录不包含问题、thread ID、Reviewer 原文或服务商错误正文。已有历史文件字节不变；会话锁释放、失败缓存清理，修正后可在同一实例继续提问。单次 CLI 返回退出码 2 和原因码，交互模式提示本轮停止后可继续输入。它是失败终态，不是正常的“资料不足”答复，也不自动写成学习反馈或长期记忆。

## 验证和复现

新增 **9/9 项测试**，其中一项参数化覆盖 **32 种无效回执**，另含 **2 种未应用的修改**；不要把参数案例数和 unittest 方法数混称。正常批准、完整 JSON 围栏、有效升级/修订、原严格路线不降级、旧历史保留、锁释放、传输重试、CLI 脱敏和通用解析兼容均已测。

补充反例时有一次回归仅失败于测试分类：深层数组在本机可以正常解析，产品按“非对象”正确拒绝，测试却期待“语法错误”。已改用真正截断的回执验证语法失败，没有放宽产品校验；另测超长整数触发的解析资源错误，仍返回受控失败而非原始 traceback。

完整工作副本 **229/229**（132.266 秒）；一键入口验收增加坏路线复核案例，现 **10/10**。工作流相邻边依然只观察到声明 14 条中的 9 条，完整节点序列依然 1 种；此次在工作流前中断，不代表提高系统路径覆盖率。回归修改的示例 Ledger 已恢复至固定上游 SHA-256。真实千问请求 **0**，本机预占保持 **15/100**。

从仓库根目录运行现有 `scripts/verify_learning_paths.py` 即可看到新增的 `invalid_route_review` 终态。针对性测试：

```powershell
Set-Location workbench\deepreason
$env:PYTHONPATH='src'
..\..\.venv\Scripts\python.exe -m unittest tests.test_learning_route_review -v
```

预期 9 项 OK，坏回执仅经过 route/reviewer，安全终态落盘，没有新增模型生成和会话提交。测试中的 SQLite 计数使用临时假客户端计数库，不消耗本机真实千问计数。

## 未完成与下一入口

真实千问遵循新格式的能力、误拦与语义风险尚未验证；上次 HTTP 403 后本轮没有再次请求。不能宣称这个校验已经提高答案准确率。原通用 Web/CLI 的宽松 Reviewer 行为也未全局更改，保护范围是学习入口。

下一工作包 **S1.2**：普通 guided 答案目前仍只经过 Gate，须复用现有最终 Reviewer 保护真正生成的答案；无资料和拒绝说明不额外调用模型。需要比较正确答案发布、坏审查扣稿、草稿不入会话以及新增调用代价。本课没有提前把这一项写成完成。

归属：原模型调用、重试、路由只升级与异常主路径来自上游/此前适配；原始回执校验、学习失败终态、CLI 接线、故障实验及教学说明由本项目与 AI 协作新增。
