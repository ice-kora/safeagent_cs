# 02 技术与架构文档

## 1. 架构目标

本项目的架构目标不是做大而全平台，而是构建一个具有企业级设计标准的 Agent 控制内核。

核心要求：

- Agent 与业务系统隔离
- LLM 不直接执行工具
- P0 默认 Rule Mode，LLM Mode 仅作为 P0.5 可选增强
- ActionPlan 必须经过 ActionPlanValidator
- 权限控制独立于模型
- PolicyService 可以读取 RepositoryService 的只读权限上下文
- 工具调用网关化
- 失败处理标准化
- Trace 全链路记录
- LoggingService 写入脱敏应用日志
- Mock 外部平台降低实现成本
- 核心逻辑可测试

## 2. 总体架构

```text
Client / Channel
  ↓
Channel Adapter
  ↓
FastAPI Chat API
  ↓
MessageNormalizer
  ↓
LangGraph Agent Workflow
  ↓
InputGuard
  ↓
IntentClassifier
  ↓
ActionPlanner
  ↓
ActionPlanValidator
  ↓
PolicyService
  ↓
RepositoryService 只读权限预检
  ↓
ToolGateway
  ↓
Mock Business Tools
  ↓
FailureHandler / TicketService / ResponseGenerator
  ↓
TraceLog / LoggingService / AuditLog
```

## 3. 分层设计

### 3.1 接入层

负责接收外部消息。

P0：

- HTTP API
- CLI Demo

P1：

- Telegram Adapter
- Slack Adapter
- Feishu Adapter

设计原则：

- 接入层只做消息适配
- 不包含 Agent 业务逻辑
- 所有渠道统一转成 NormalizedMessage

### 3.2 Agent 编排层

使用 LangGraph 实现。

核心节点：

- normalize_message
- input_guard
- classify_intent
- plan_action
- validate_action_plan
- policy_check
- save_pending_action
- tool_gateway
- failure_handler
- create_ticket
- generate_response
- save_trace

P0 使用真实 LangGraph StateGraph 编排，但不实现复杂 checkpoint、长期记忆、复杂 interrupt 恢复或复杂子图。如果环境问题导致 LangGraph 无法落地，才允许临时实现 LangGraph-compatible workflow，并在 README 中说明。

### 3.3 策略层

由 PolicyService 实现。

职责：

- 判断动作是否允许
- 判断风险等级
- 判断是否需要用户确认
- 判断是否需要人工接管
- 默认拒绝未知动作
- 读取 RepositoryService 的只读权限上下文

PolicyService 不允许修改订单、创建工单、执行退款、调用业务工具或返回敏感字段。

### 3.4 计划校验层

由 ActionPlanValidator 实现。

职责：

- 校验 Planner 或 LLM 输出是否为合法 JSON
- 校验 action 是否在允许集合中
- 校验 target_type 是否合法
- 校验 tool_name 是否在候选工具集合中
- 校验必要参数是否存在
- 校验明显危险动作
- 返回 PLAN_INVALID 或 UNKNOWN_ACTION

ActionPlanValidator 不判断订单归属、租户一致性、业务状态或风险等级。

### 3.5 工具层

由 ToolGateway 统一调用。

职责：

- 工具白名单检查
- 参数校验
- 权限结果校验
- 单次工具执行
- 结果脱敏
- 工具调用日志记录
- 记录 run_id、tool_name、attempt_no、status、failure_type、latency_ms

ToolGateway 不负责重试、降级或创建工单。重试由 FailureHandler 决定。

### 3.6 Repository 层

由 RepositoryService 提供只读权限预检数据。

建议方法：

- `get_order_auth_context(order_id)`
- `get_user_context(user_id)`
- `get_open_ticket_by_idempotency_key(idempotency_key)`

RepositoryService 不暴露完整订单对象，不返回完整手机号、完整地址、支付信息等敏感字段。

### 3.7 Pending Action 层

由 PendingActionService 实现。

职责：

- 保存 CONFIRM_REQUIRED 对应的 ActionPlan
- 生成 pending_action_id
- 使用 SQLite 持久化
- 默认 10 分钟过期
- 支持 PENDING、CONFIRMED、EXECUTED、EXPIRED、CANCELLED 状态

`POST /api/confirm` 会创建新的 run_id，并通过 parent_run_id 关联原始 run。

### 3.8 Mock 业务层

模拟真实业务平台。

包含：

- 用户数据
- 订单数据
- 物流数据
- 工单数据
- 知识库数据
- 失败场景配置

### 3.9 观测层

包含：

- agent_traces
- policy_logs
- tool_call_logs
- failure_logs
- security_logs
- logs/application.log

## 4. 技术选型

### 4.1 FastAPI

用途：

- 提供 HTTP API
- 暴露聊天接口
- 暴露 Trace 查询
- 暴露工单查询

选择原因：

- Python 生态适合 Agent 项目
- 开发速度快
- API 定义清晰
- 与 pytest 配合方便

### 4.2 LangGraph

用途：

- 编排 Agent 工作流
- 实现条件路由
- 实现可中断流程
- 管理状态流转

选择原因：

- 比简单链式调用更适合复杂流程
- 适合权限检查、工具调用、失败处理、人工接管等分支场景
- 与本项目的受控 Agent 闭环高度匹配

### 4.3 LangChain

用途：

- P1 可选真正 RAG 知识库实现
- 文档加载、切分、检索、生成回答

选择原因：

- 快速构建客服政策问答
- 适合作为知识工具，而不是系统主控制层

P0 不使用 LangChain 做真正 RAG。P0 只实现 KnowledgeTool + 静态知识库 + sources。

### 4.4 SQLite

用途：

- 存储用户、订单、工单、Trace、日志

选择原因：

- 轻量
- 适合个人 MVP
- 便于本地运行
- 比纯 JSON 更接近企业项目数据结构

### 4.5 JSON Mock

用途：

- 模拟外部订单、物流、用户、失败场景

选择原因：

- 降低外部依赖
- 让项目聚焦 Agent 核心
- 方便构造失败场景

### 4.6 pytest

用途：

- 验证 PolicyService
- 验证 ToolGateway
- 验证失败处理
- 验证 Agent 流程

选择原因：

- 企业项目基本测试能力
- 面试讲解时可以证明可靠性

## 5. 为什么不用完整客服平台

原因：

- 时间只有三天
- 完整客服平台开发量过大
- 项目目标是 Agent 控制内核，不是 CRUD 平台
- 外部平台用 Mock Tool 更能突出 Agent 能力

## 6. 为什么不用传统规则树直接做完

传统规则树适合高频确定性场景，但复杂客服场景存在：

- 多意图混合
- 长尾问题
- 用户表达不规范
- 需要动态检索知识
- 需要跨系统编排

因此本项目采用：

```text
传统规则 + 受控 Agent
```

而不是：

```text
纯 LLM 决策
```

## 7. 核心设计约束

- `ActionPlan` 是模型产物，不可信。
- `ActionPlanValidator` 只判断计划是否像一个合法计划。
- `PolicyDecision` 是后端策略产物，可信。
- `PolicyService` 决定当前用户能不能做、风险多高。
- `ToolResult` 不能直接暴露敏感字段。
- `UnknownAction` 必须拒绝。
- `HighRiskAction` 必须转人工。
- `TraceLog` 必须记录所有关键节点。
- `ToolGateway` 每次只执行一次工具调用。
- `FailureHandler` 负责重试、降级和失败日志。
- LLMResponseGenerator 只能接收脱敏安全摘要，不能改变业务结论。

## 8. 推荐目录结构

```text
safeagent_cs/
├── app/
│   ├── main.py
│   ├── api/
│   ├── graph/
│   ├── core/
│   ├── services/
│   ├── tools/
│   ├── adapters/
│   ├── mock_platform/
│   └── storage/
├── tests/
├── docs/
├── demo.py
├── README.md
└── requirements.txt
```

关键新增文件包括：

- `app/core/action_plan_validator.py`
- `app/services/repository_service.py`
- `app/services/pending_action_service.py`
- `app/services/logging_service.py`
- `app/api/confirm.py`
