# 09 Codex 开发任务文档

## 1. 项目任务

请实现一个项目：

SafeAgent-CS：面向复杂客服场景的企业级受控 Agent 最小闭环系统。

重点不是完整客服平台，而是 Agent 控制内核。

必须实现：

- LangGraph Agent 工作流
- ActionPlan
- ActionPlanValidator
- PolicyService
- RepositoryService 只读权限预检
- ToolGateway
- Mock Business Tools
- FailureHandler
- TicketService
- PendingActionService
- TraceLog
- LoggingService
- FastAPI 接口
- pytest 测试
- Demo 脚本

## 2. 开发总原则

必须遵守：

1. LLM 不能直接调用工具。
2. P0 默认 Rule Mode，不能把项目改成纯 LLM 项目。
3. ActionPlanner 只能生成候选 ActionPlan。
4. ActionPlan 必须经过 ActionPlanValidator。
5. 所有工具调用必须经过 PolicyService。
6. 所有工具调用必须经过 ToolGateway。
7. 未知动作默认拒绝。
8. 高风险动作转人工。
9. 工具失败进入 FailureHandler。
10. 所有关键节点写 TraceLog 和结构化日志。
11. 不要只做成功路径。
12. 不要把所有代码写进 main.py。

## 3. 禁止事项

不要实现：

- 真实支付
- 真实退款
- 真实登录系统
- 复杂前端
- 真实第三方客服系统
- 复杂权限后台
- 客服排班系统
- 大而全 CRM

不要做：

- LLM 直接执行业务工具
- 跳过 PolicyService
- 跳过 ToolGateway
- 只做聊天回复
- 只做 FAQ
- 没有测试
- 没有失败处理
- 没有 Trace
- 跳过 ActionPlanValidator
- 跳过日志脱敏
- 把真正 RAG 放进 P0

## 4. 推荐目录结构

```text
safeagent_cs/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── chat.py
│   │   ├── confirm.py
│   │   ├── trace.py
│   │   ├── tickets.py
│   │   ├── mock.py
│   │   └── health.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── router.py
│   │   └── workflow.py
│   ├── core/
│   │   ├── action_plan.py
│   │   ├── action_plan_validator.py
│   │   ├── policy.py
│   │   ├── risk.py
│   │   ├── errors.py
│   │   └── constants.py
│   ├── services/
│   │   ├── input_guard.py
│   │   ├── intent_service.py
│   │   ├── planner_service.py
│   │   ├── policy_service.py
│   │   ├── repository_service.py
│   │   ├── tool_gateway.py
│   │   ├── failure_handler.py
│   │   ├── response_service.py
│   │   ├── ticket_service.py
│   │   ├── pending_action_service.py
│   │   ├── logging_service.py
│   │   └── trace_service.py
│   ├── tools/
│   │   ├── order_tool.py
│   │   ├── logistics_tool.py
│   │   ├── user_tool.py
│   │   ├── refund_tool.py
│   │   ├── ticket_tool.py
│   │   └── knowledge_tool.py
│   ├── adapters/
│   │   ├── base.py
│   │   ├── cli_adapter.py
│   │   └── telegram_adapter.py
│   ├── mock_platform/
│   │   ├── mock_orders.json
│   │   ├── mock_users.json
│   │   ├── mock_tickets.json
│   │   ├── knowledge_docs/
│   │   └── failure_scenarios.json
│   ├── logs/
│   └── storage/
│       ├── db.py
│       └── models.py
├── tests/
│   ├── test_policy.py
│   ├── test_tool_gateway.py
│   ├── test_failure_scenarios.py
│   ├── test_red_team.py
│   └── test_agent_flow.py
├── docs/
├── demo.py
├── README.md
└── requirements.txt
```

## 5. 开发阶段

### 阶段 1：项目骨架

交付：

- 目录结构
- FastAPI main
- health API
- 基础模型
- requirements.txt
- README 运行说明

验收：

```bash
uvicorn app.main:app --reload
GET /api/health
```

### 阶段 2：核心数据结构

交付：

- CustomerAgentState
- ActionPlan
- ActionPlanValidator
- PolicyDecision
- FailureType
- RiskLevel
- request_id / session_id / run_id / parent_run_id / trace_node_id
- Mock users/orders

验收：

- 类型清晰
- 可单元测试

### 阶段 3：RepositoryService 与 LoggingService

交付：

- RepositoryService 只读权限上下文
- get_order_auth_context
- get_user_context
- get_open_ticket_by_idempotency_key
- LoggingService
- logs/application.log
- 日志脱敏

验收：

- 不返回完整订单对象
- 不记录完整手机号、完整地址、token、系统 Prompt

### 阶段 4：PolicyService

交付：

- query_policy
- query_order
- change_address
- request_refund
- complaint
- unknown_action
- prompt_injection

验收：

- test_policy.py 通过
- PolicyService 只读取 RepositoryService，不调用业务工具
- 接入完整链路前，PolicyService.evaluate 每次裁决必须写 policy_logs

### 阶段 5：ToolGateway

交付：

- 工具白名单
- 参数校验
- 权限校验
- 工具调用日志
- 结果脱敏
- 单次工具调用
- attempt_no / latency_ms

验收：

- 未授权不得调用
- 未知工具拒绝
- 结果脱敏
- 不在 ToolGateway 内部写死重试

### 阶段 6：Mock Tools

交付：

- order_tool
- ticket_tool
- knowledge_tool
- logistics_tool
- failure_scenario 支持

验收：

- 正常返回
- 可模拟超时、500、错误字段

### 阶段 7：PendingActionService 与 /api/confirm

交付：

- pending_actions SQLite 表
- pending_action_id
- 10 分钟过期
- POST /api/confirm
- confirm 创建新的 run_id
- parent_run_id 关联原始 run

验收：

- CONFIRM_REQUIRED 能恢复执行
- 用户不匹配或过期时拒绝

### 阶段 8：LangGraph 工作流

交付：

- nodes
- router
- workflow
- /api/chat 接入

验收：

- 8 个 Demo 可跑

### 阶段 9：FailureHandler

交付：

- TOOL_TIMEOUT
- TOOL_5XX
- TOOL_BAD_RESPONSE
- PARAM_MISSING
- RAG_EMPTY
- DUPLICATE_OPERATION
- PROMPT_INJECTION

验收：

- 工具失败不崩溃
- 可以降级或转人工
- 重试由 FailureHandler 调用 ToolGateway 实现

### 阶段 10：TraceLog 与日志表

交付：

- 每个节点写 Trace
- GET /api/traces/{run_id}
- policy_logs
- tool_call_logs
- failure_logs
- security_logs

验收：

- 每次 chat 和 confirm 都能通过 run_id 查 Trace
- 日志脱敏

### 阶段 11：测试

交付：

- 20 条以上测试
- pytest 全通过

验收：

```bash
pytest
```

### 阶段 12：Demo

交付：

- demo.py
- 8 个场景
- README 演示说明

验收：

- 可按顺序演示全部场景

## 6. 实现策略

三天时间有限，P0 使用 Rule Mode，默认启用规则型 IntentClassifier 和 ActionPlanner。项目不能完全不接真实 LLM 的扩展口径，但真实 LLM 放在 P0.5，可选增强，不能影响 P0 验收。

允许：

- 用规则/关键词模拟 LLM 的意图识别
- 用结构化函数生成 ActionPlan
- P0.5 通过 LLMIntentClassifier、LLMActionPlanner、LLMResponseGenerator 增强展示能力

不允许：

- 让系统逻辑依赖不可控模型输出
- 因为没有真实 LLM 而跳过 PolicyService
- 让 LLM 覆盖 DENY / HUMAN_REQUIRED
- 让 LLM 直接调用工具

## 7. 最小接口

必须实现：

```text
POST /api/chat
POST /api/confirm
GET /api/traces/{run_id}
GET /api/tickets
GET /api/tickets/{ticket_id}
POST /api/mock/failure-mode
GET /api/health
```

## 8. 最小测试要求

必须实现：

- 8 条 PolicyService 测试
- 5 条 ToolGateway 测试
- 5 条失败场景测试
- 3 条红队攻击测试
- 3 条 Agent 流程测试

## 9. 最终验收

项目完成条件：

- 代码可运行
- API 可调用
- 8 个 Demo 可演示
- pytest 通过
- Trace 可查询
- 越权被拒绝
- 退款转人工
- 工具失败可降级

## 10. 技术债

P0.5 接入 LLM Mode 时，ActionPlanValidator 需要增加对 `tool_args` 和 `reason` 的危险词扫描。P0 当前只拦截 forbidden action 可以接受。
