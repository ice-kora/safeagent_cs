# 10 开发期间学习与检查指南

## 1. 你的角色

在 Codex 写代码期间，你不是旁观者，而是项目 Owner。

你需要做三件事：

1. 控制方向：防止 Codex 写偏。
2. 啃核心：理解 Agent 主链路。
3. 验收质量：用测试和 Demo 检查系统是否成立。

## 2. 不要做什么

不要一开始就逐行啃全部代码。

三天内如果你逐行看所有文件，会被拖死。

不要纠结：

- UI 是否好看
- 是否接真实平台
- 数据库是否完美
- 类型是否极致优雅
- 是否一开始就接真实 LLM

你要先抓主链路。

## 3. 第一优先级：啃八个核心文件

Codex 生成后，你优先读：

```text
app/graph/state.py
app/graph/workflow.py
app/core/action_plan_validator.py
app/services/repository_service.py
app/services/policy_service.py
app/services/tool_gateway.py
app/services/failure_handler.py
app/services/pending_action_service.py
app/services/logging_service.py
```

这些文件决定项目是否成立。

## 4. 你要画出一张流程图

看代码时，手写或记录：

```text
用户消息进入哪里？
State 如何创建？
哪个节点识别意图？
哪个节点生成 ActionPlan？
ActionPlan 在哪里校验？
哪个节点做权限判断？
PolicyService 从哪里读取只读权限上下文？
哪个节点调用工具？
失败后走哪里？
CONFIRM_REQUIRED 后 pending_action_id 保存在哪里？
/api/confirm 如何创建新的 run_id？
最后怎么回复？
Trace 在哪里记录？
```

## 5. 每个模块你要问自己的问题

### 5.1 State

你要搞懂：

- State 有哪些字段？
- 哪些字段来自用户？
- 哪些字段来自 Agent？
- 哪些字段来自策略系统？
- 哪些字段来自工具？
- 哪些字段最终返回给用户？

### 5.2 PolicyService

你要搞懂：

- 它为什么不能交给 LLM？
- 它如何判断本人订单？
- 它从 RepositoryService 读取哪些只读字段？
- 它如何判断高风险？
- 它如何默认拒绝未知动作？
- 它返回什么结构？

### 5.3 ToolGateway

你要搞懂：

- 为什么不能直接调用 tool？
- 它检查了什么？
- 它在哪里做脱敏？
- 它如何只执行一次工具调用？
- 它如何记录 attempt_no、latency_ms？
- 它是否记录日志？

### 5.4 FailureHandler

你要搞懂：

- 工具超时怎么处理？
- 500 怎么处理？
- 重试为什么在 FailureHandler 而不是 ToolGateway？
- 参数缺失怎么处理？
- 静态知识库空结果怎么处理？
- 什么时候转人工？

### 5.6 PendingActionService

你要搞懂：

- pending_action_id 如何生成？
- pending_actions 为什么要落 SQLite？
- 10 分钟过期在哪里判断？
- `/api/confirm` 为什么创建新的 run_id？
- parent_run_id 如何关联原始 run？

### 5.7 ActionPlanValidator

你要搞懂：

- Validator 校验哪些结构问题？
- Validator 为什么不判断订单归属？
- Validator 失败时如何返回 PLAN_INVALID 或 UNKNOWN_ACTION？
- LLM 输出非法 JSON 时如何降级到 Rule Mode？

### 5.5 Workflow

你要搞懂：

- LangGraph 节点有哪些？
- 条件路由在哪里？
- DENY 走哪里？
- ALLOW 走哪里？
- HUMAN_REQUIRED 走哪里？
- CONFIRM_REQUIRED 走哪里？

## 6. 每半天验收一次

### 第一次验收

目标：

- 项目能启动
- /api/health 正常
- 目录结构合理

### 第二次验收

目标：

- PolicyService 测试通过
- ToolGateway 测试通过

### 第三次验收

目标：

- /api/chat 能跑本人订单查询
- Trace 有记录
- GET /api/traces/{run_id} 可查

### 第四次验收

目标：

- 查询他人订单被拒绝
- 退款转人工
- 工具失败能降级
- `/api/confirm` 能恢复执行待确认动作
- 日志中没有敏感明文

## 7. 你要准备的面试讲解

最终你要能讲清：

```text
1. 为什么这个项目不是普通客服机器人？
2. 为什么 LLM 不能直接调用工具？
3. PolicyService 解决什么问题？
4. ToolGateway 解决什么问题？
5. FailureHandler 为什么重要？
6. TraceLog 如何支撑可观测性？
7. 传统客服和 Agent 客服如何协同？
8. 这个项目有哪些边界？
9. 为什么 P0 是 Rule Mode，P0.5 才是 LLM Mode？
10. 为什么 P0 不做真正 RAG？
```

## 8. 你的学习顺序

建议顺序：

```text
1. 看 README 和架构图
2. 看 State
3. 看 ActionPlanValidator
4. 看 RepositoryService
5. 看 PolicyService
6. 看 ToolGateway
7. 看 Workflow
8. 看 FailureHandler
9. 看 PendingActionService
10. 跑 Demo
11. 看测试
12. 修改一个小规则
13. 新增一个测试用例
```

## 9. 你必须亲手做的小改动

不要只看。

你至少亲手做三件事：

1. 新增一个 Policy 规则。
2. 新增一个失败场景。
3. 新增一个测试用例。

这样这个项目才会进入你的脑子。

## 10. 最终自检

如果你能不看代码讲出：

```text
用户查询他人订单时，系统从 API 到 PolicyService 到 ToolGateway 到 ResponseGenerator 的完整链路。
```

说明你真正掌握了项目核心。

如果你还能讲出：

```text
工具超时后 FailureHandler 如何降级并创建工单。
```

说明你已经达到面试可讲水平。
