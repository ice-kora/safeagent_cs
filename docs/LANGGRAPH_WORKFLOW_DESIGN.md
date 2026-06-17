# SafeAgent-CS LangGraph Workflow 接入设计

本文档定义 SafeAgent-CS 后续接入 LangGraph 的第一阶段设计边界。

当前阶段只讨论 `/api/chat` 主流程的 Workflow 化，不实现代码、不新增依赖、不改 `/api/confirm` 恢复语义。

一句话定位：

```text
LangGraph 是流程编排层，不是权限裁决层，也不是工具执行层。
```

核心原则：

- LangGraph 只替代 `/api/chat` 中的手写流程编排。
- LangGraph 不替代 `ActionPlanValidator`。
- LangGraph 不替代 `PolicyService`。
- LangGraph 不替代 `ToolGateway`。
- LangGraph 不替代 `PendingActionService`。
- LangGraph 不替代 `FailureHandler`。
- LangGraph 不替代 `TraceService` / `LoggingService`。
- LangGraph 不替代 `LLMOutputGuard` / `LLMResponseGuard`。

## 1. 当前 P0 / P0.5 状态回顾

当前 P0 `/api/chat` 主流程：

```text
/api/chat
-> IntentClassifier
-> ActionPlanner
-> ActionPlanValidator
-> PolicyService
-> ToolGateway / PendingAction / HumanRequired / Deny
-> FailureHandler
-> Trace / Logs
```

当前 `/api/chat` 已经能完成受控 Agent 最小闭环：

- 创建 `request_id` 和 `run_id`。
- 执行规则意图识别。
- 生成候选 `ActionPlan`。
- 校验 `ActionPlan` 结构。
- 通过 `PolicyService` 做权限与风险裁决。
- `ALLOW` 分支通过 `ToolGateway` 调用工具。
- `CONFIRM_REQUIRED` 分支创建 `pending_action`。
- `HUMAN_REQUIRED` 分支返回人工处理结果。
- `DENY` 分支拒绝执行。
- 工具失败交由 `FailureHandler` 收口。
- 全链路写入 Trace 和结构化日志。

当前 P0.5 已有：

- LLM schema 契约。
- `LLMOutputGuard` 基础校验。
- `LLMResponseGuard` 基础校验。

当前 P0.5 尚未接入：

- 真实 LLM。
- `LLMIntentClassifier`。
- `LLMActionPlanner`。
- `LLMResponseGenerator`。
- LangGraph Workflow。

## 2. 为什么引入 LangGraph

引入 LangGraph 的目标不是让系统更“智能”，而是让流程编排更清晰、更可演进。

主要目标：

1. 将 `/api/chat` 中的手写 if/else 主流程拆成节点。
2. 明确每个节点的输入输出。
3. 支持条件分支，例如 `ALLOW`、`DENY`、`CONFIRM_REQUIRED`、`HUMAN_REQUIRED`。
4. 支持中断与恢复设计，为后续 interrupt / resume 打基础。
5. 支持 Trace 节点化，让每个 Workflow 节点自然对应一个 Trace 节点。
6. 为后续更复杂 Agent Workflow 做准备。

LangGraph 的价值在流程组织，不在业务裁决。它可以让主流程从“一个较长的函数”变成“可观测、可测试、可替换的节点图”。

## 3. LangGraph 不负责什么

LangGraph 不做权限裁决。

权限裁决仍由 `PolicyService` 负责。LangGraph 节点只能调用 `PolicyService`，不能在图内部重新实现用户归属、租户一致性或业务状态判断。

LangGraph 不直接调用具体工具。

工具调用仍必须经过 `ToolGateway`。Workflow 节点不能直接调用 `order_tool`、`knowledge_tool`、`ticket_tool` 或未来真实业务工具。

LangGraph 不绕过 `ToolGateway`。

即使后续加入真实工具、平台接口或 MCP 工具目录，工具执行入口仍然必须受 `ToolGateway` 控制。

LangGraph 不重新实现 `PolicyService`。

策略规则、风险等级和权限判断不能散落到 Workflow 节点中。节点只负责传递输入、调用服务、记录结果。

LangGraph 不重新实现 `PendingActionService`。

二次确认动作的创建、状态更新、过期判断和用户校验仍由 `PendingActionService` 负责。

LangGraph 不替代 `/api/confirm` 的 `pending_action` 恢复语义。

`/api/confirm` 当前是确认恢复入口，不重新理解用户意图，不重新规划动作。后续是否 Workflow 化需要单独设计。

LangGraph 不让 LLM Planner 的输出直接进入工具执行。

只要启用 LLM Planner，输出必须先经过 `LLMOutputGuard`，再经过 `ActionPlanValidator`，再经过 `PolicyService`，最后才可能进入 `ToolGateway`。

## 4. 推荐节点设计

### mode_router_node

职责：

- 读取运行模式。
- 生成 `ModeDecision`。
- 决定后续使用 Rule Mode 还是 LLM Mode / Hybrid Mode。

输入：

- request context
- `SAFEAGENT_MODE`
- LLM 配置状态

输出：

- `ModeDecision`
- `requested_mode`
- `effective_mode`
- `fallback_reason_code`
- `fallback_reason`

不负责：

- 不识别具体业务意图。
- 不生成 `ActionPlan`。
- 不判断权限。

复用 service：

- 后续可复用 `ModeRouter`。
- 当前 P0 可先使用现有 Rule Mode 配置。

### intent_node

职责：

- 根据模式执行意图识别。
- Rule Mode 下调用 `RuleBasedIntentClassifier`。
- LLM Mode 下后续可调用 `LLMIntentClassifier`。

输入：

- user message
- `ModeDecision`

输出：

- intent
- entities
- confidence

不负责：

- 不判断权限。
- 不决定是否调用工具。
- 不生成最终回复。

复用 service：

- `RuleBasedIntentClassifier`
- 后续 `LLMIntentClassifier`

### planner_node

职责：

- 根据 intent 和 message 生成候选 `ActionPlan`。
- Rule Mode 下调用 `RuleBasedActionPlanner`。
- LLM Mode 下后续可调用 `LLMActionPlanner`。

输入：

- user message
- intent
- entities
- `ModeDecision`

输出：

- 候选 `ActionPlan`
- 或 LLM 生成的 `LLMActionPlanCandidate`

不负责：

- 不判断订单归属。
- 不判断风险等级。
- 不执行工具。

复用 service：

- `RuleBasedActionPlanner`
- 后续 `LLMActionPlanner`

### llm_output_guard_node

职责：

- 校验 LLM 原始输出。
- 只在启用 LLM Planner 输出时强制执行。
- Rule Mode 下可以跳过。

输入：

- LLM raw output
- `LLMActionPlanCandidate`

输出：

- `LLMGuardResult`
- sanitized payload
- fallback decision

不负责：

- 不替代 `ActionPlanValidator`。
- 不判断权限。
- 不执行工具。

复用 service：

- `LLMOutputGuard`

### action_plan_validator_node

职责：

- 校验系统内部 `ActionPlan` 结构。
- 确保 action、target_type、tool_name、必要参数符合规则。

输入：

- `ActionPlan`

输出：

- validation result

不负责：

- 不判断订单是否属于当前用户。
- 不判断租户一致性。
- 不判断是否需要人工。

复用 service：

- `ActionPlanValidator`

### policy_node

职责：

- 执行权限与风险裁决。
- 返回 `ALLOW`、`DENY`、`CONFIRM_REQUIRED` 或 `HUMAN_REQUIRED`。

输入：

- `ActionPlan`
- customer_user_id
- session context

输出：

- `PolicyDecision`

不负责：

- 不调用工具。
- 不创建 pending action。
- 不生成最终回复。

复用 service：

- `PolicyService`
- `RepositoryService`

### route_by_policy_node

职责：

- 根据 `PolicyDecision` 决定下一跳节点。

输入：

- `PolicyDecision`

输出：

- route key：`ALLOW` / `CONFIRM_REQUIRED` / `HUMAN_REQUIRED` / `DENY`

不负责：

- 不修改策略结果。
- 不补充权限判断。
- 不调用工具。

复用 service：

- 不需要独立业务 service。

### tool_gateway_node

职责：

- 在 `ALLOW` 分支调用工具。
- 所有工具调用必须经过 `ToolGateway`。
- 写入 `tool_call_logs`。

输入：

- run_id
- session_id
- tool_name
- tool_args

输出：

- `ToolResult`

不负责：

- 不判断权限。
- 不判断是否重试。
- 不直接调用 Mock Tool。

复用 service：

- `ToolGateway`

### pending_action_node

职责：

- 在 `CONFIRM_REQUIRED` 分支创建 `pending_action`。
- 保存候选 `ActionPlan` 快照。

输入：

- session_id
- source_run_id
- user_id
- `ActionPlan`
- risk_level

输出：

- pending_action_id

不负责：

- 不执行工具。
- 不做权限复核。
- 不生成新的 run。

复用 service：

- `PendingActionService`

### human_required_node

职责：

- 在 `HUMAN_REQUIRED` 分支生成安全处理结果。
- P0 阶段可只返回人工处理状态。

输入：

- `PolicyDecision`
- `ActionPlan`

输出：

- human required response context

不负责：

- 不直接创建复杂工单流转。
- 不绕过 `ToolGateway` 创建工单。
- 不改变策略结论。

复用 service：

- 当前可不依赖额外 service。
- 后续若创建工单，必须通过 `ToolGateway`。

### deny_node

职责：

- 在 `DENY` 分支生成拒绝执行结果。

输入：

- `PolicyDecision`
- `ActionPlan`

输出：

- deny response context

不负责：

- 不调用工具。
- 不创建 pending action。
- 不改写策略结论。

复用 service：

- 当前可不依赖额外 service。

### failure_handler_node

职责：

- 处理 `ToolGateway` 返回的失败结果。
- 判断是否需要受控重试或失败收口。

输入：

- `ToolResult`
- run_id
- session_id
- tool_name
- tool_args

输出：

- `FailureHandlingResult`

不负责：

- 不判断权限。
- 不直接调用具体工具。
- 不生成最终用户回复。

复用 service：

- `FailureHandler`
- 重试仍通过 `ToolGateway`

### response_generation_node

职责：

- 生成最终回复草稿或规则回复。
- Rule Mode 下可使用固定规则回复。
- LLM Response Mode 下后续可调用 `LLMResponseGenerator`。

输入：

- status
- intent
- action
- `PolicyDecision`
- `ToolResult`
- `FailureHandlingResult`
- pending_action_id
- public_reason
- safe_summary

输出：

- response text 或 `LLMResponseDraft`

不负责：

- 不改变业务状态。
- 不改变策略结论。
- 不声明未发生的工具成功。

复用 service：

- 后续 `LLMResponseGenerator`
- 当前规则响应逻辑

### llm_response_guard_node

职责：

- 校验 LLM 回复草稿是否安全。
- 只在启用 LLM 回复草稿时执行。

输入：

- `LLMResponseDraft`
- expected_status
- expected_policy_decision
- tool_result_success
- rule_based_response

输出：

- `LLMGuardResult`
- safe response

不负责：

- 不调用 LLM。
- 不判断权限。
- 不访问数据库。

复用 service：

- `LLMResponseGuard`

### finish_node

职责：

- 汇总 Workflow 结果。
- 调用 `TraceService.finish_run` 或 `TraceService.fail_run`。
- 生成 `/api/chat` 统一响应结构。

输入：

- workflow state
- final status
- response text
- run_id

输出：

- API response payload

不负责：

- 不补做业务判断。
- 不调用工具。
- 不修改 pending action 状态。

复用 service：

- `TraceService`
- `LoggingService`

## 5. Workflow 主路径

推荐主路径：

```text
START
-> mode_router_node
-> intent_node
-> planner_node
-> llm_output_guard_node
-> action_plan_validator_node
-> policy_node
-> route_by_policy_node
    -> ALLOW -> tool_gateway_node -> failure_handler_node -> response_generation_node -> llm_response_guard_node -> finish_node
    -> CONFIRM_REQUIRED -> pending_action_node -> response_generation_node -> llm_response_guard_node -> finish_node
    -> HUMAN_REQUIRED -> human_required_node -> response_generation_node -> llm_response_guard_node -> finish_node
    -> DENY -> deny_node -> response_generation_node -> llm_response_guard_node -> finish_node
END
```

执行规则：

- Rule Mode 下可以跳过 `llm_output_guard_node`。
- 如果没有启用 LLM 回复草稿，也可以跳过 `llm_response_guard_node`。
- 只要启用 LLM Planner 输出，就必须经过 `LLMOutputGuard`。
- 只要启用 LLM 回复草稿，就必须经过 `LLMResponseGuard`。
- `route_by_policy_node` 只能根据 `PolicyDecision` 分支，不能改写策略结果。
- 所有工具调用仍必须经过 `ToolGateway`。

## 6. /api/chat 与 LangGraph 的关系

`/api/chat` 仍然是 HTTP 入口。

LangGraph 只是在 `/api/chat` 内部替代手写流程编排。HTTP 层的职责不应被 LangGraph 吞掉。

`/api/chat` 继续负责：

- 接收请求。
- 校验请求基础字段。
- 创建 `request_id`。
- 创建 `run_id`。
- 初始化 Workflow state。
- 调用 Workflow。
- 返回统一响应。

Workflow 内部节点继续负责：

- 调用对应 service。
- 写入节点级 Trace。
- 传递结构化 state。
- 按条件分支路由。
- 将最终结果交给 `finish_node` 汇总。

Workflow 结束后，`/api/chat` 返回与当前 P0 兼容的响应结构，避免破坏调用方。

## 7. /api/confirm 与 LangGraph 的关系

`/api/confirm` 当前不建议立即改成 LangGraph。

原因：

- `/api/confirm` 是 `pending_action` 恢复入口。
- 它不是新的意图识别入口。
- 它不重新调用 `IntentClassifier`。
- 它不重新调用 `ActionPlanner`。
- 它不重新调用 LLM Planner。
- 它读取 `action_plan_json` 后重新走 `PolicyService` 复核，再通过 `ToolGateway` 执行。

当前 `/api/confirm` 的核心语义应保持：

```text
validate_pending_action
-> 读取 action_plan_json
-> PolicyService 复核
-> ToolGateway
```

如果后续要将 `/api/confirm` Workflow 化，应单独设计确认恢复图。该图也必须保留：

- 新 `run_id`
- `parent_run_id`
- `pending_action_id`
- session_id 校验
- user_id 校验
- `PolicyService` 复核
- `ToolGateway` 受控工具调用

`/api/confirm` 是否 Workflow 化，不在 Phase 8A-1 实现范围内。

## 8. Workflow State 设计

Workflow State 是流程上下文，不是数据库实体。

候选字段：

- `request_id`
- `run_id`
- `parent_run_id`
- `session_id`
- `user_id`
- `tenant_id`
- `message`
- `mode_decision`
- `intent_result`
- `action_plan_candidate`
- `action_plan`
- `validation_result`
- `policy_decision`
- `pending_action_id`
- `tool_result`
- `failure_result`
- `response_draft`
- `response_guard_result`
- `final_response`
- `trace_events`
- `errors`

State 的边界：

- State 只保存流程推进所需的最小上下文。
- State 不应该保存完整敏感数据。
- 完整订单、完整地址、手机号、支付信息、内部异常栈、API key、token 不能进入 State。
- State 中只允许保存 ID、状态、脱敏摘要、安全结果和节点输出的结构化摘要。

State 设计原则：

1. 节点只读自己需要的字段。
2. 节点只写自己负责产出的字段。
3. `PolicyService` 所需业务上下文仍通过 `RepositoryService` 获取。
4. `ToolGateway` 所需参数仍来自通过校验的 `ActionPlan`。
5. Trace 中记录状态变化摘要，不记录完整敏感对象。

建议约束：

- `message` 可以进入 State，但写 Trace 或日志前必须脱敏。
- `tool_result` 只保留安全摘要或 `ToolResult` 的可安全序列化结果。
- `errors` 只记录错误类型和安全说明，不记录内部异常栈。

## 9. Trace 设计

每个 Workflow 节点都应写 Trace。

推荐 Trace event：

- `workflow_started`
- `mode_routing`
- `intent_classified`
- `plan_generated`
- `llm_output_guarded`
- `action_plan_validated`
- `policy_decided`
- `route_selected`
- `tool_called`
- `pending_action_created`
- `human_required`
- `denied`
- `failure_handled`
- `response_generated`
- `response_guarded`
- `workflow_finished`
- `workflow_failed`

每条 Trace 至少包含：

- `request_id`
- `run_id`
- `node_name`
- `event_type`
- `status`
- `summary`
- `created_at`

涉及 fallback 时应记录：

- `requested_mode`
- `effective_mode`
- `fallback_reason_code`
- `fallback_reason`

涉及 LLM schema 时应记录：

- `schema_version`
- `guard_status`

Trace 禁止记录：

- 完整订单对象
- 完整地址
- 手机号
- 支付信息
- API key
- token
- 系统 Prompt
- 内部异常栈

Trace 设计原则：

- Trace 是审计和排障入口，不是业务数据仓库。
- Trace 记录节点级摘要，不保存完整业务对象。
- Trace 节点名应与 Workflow 节点名稳定对应。
- `workflow_failed` 必须记录安全错误类型，但不能记录内部异常栈。

## 10. 接入策略

LangGraph 接入必须分阶段推进，不能直接把 `/api/chat` 改成 LangGraph。

### Phase 8A：只写设计文档

目标：

- 明确 LangGraph 的接入边界。
- 明确 Workflow State。
- 明确节点设计和 Trace 设计。
- 明确后续接入阶段。

禁止事项：

- 不写 LangGraph 代码。
- 不新增依赖。
- 不修改 `/api/chat`。
- 不修改 `/api/confirm`。

### Phase 8B：实现 Workflow State 与节点空壳，不接入 /api/chat

目标：

- 新增 Workflow State 数据结构。
- 新增节点函数空壳。
- 节点可以先返回模拟结果或调用现有 service 的最小路径。
- 不改变当前线上入口。

禁止事项：

- 不让 `/api/chat` 调用 LangGraph。
- 不接真实 LLM。
- 不替换现有手写编排。

### Phase 8C：用测试驱动单独跑 Workflow

目标：

- 在测试中独立运行 Workflow。
- 覆盖 `ALLOW`、`DENY`、`CONFIRM_REQUIRED`、`HUMAN_REQUIRED` 分支。
- 验证节点 Trace。
- 验证 Workflow 不绕过 Validator、PolicyService、ToolGateway。

禁止事项：

- 不接入 `/api/chat`。
- 不修改 `/api/confirm`。
- 不改变当前 Demo 行为。

### Phase 8D：在配置开关下让 /api/chat 可选走 Workflow

目标：

- 新增配置开关 `SAFEAGENT_WORKFLOW_MODE`。
- `manual` 模式继续走当前手写编排。
- `langgraph` 模式才走 LangGraph Workflow。
- 通过测试证明两种模式行为一致。

禁止事项：

- 不删除 manual 模式。
- 不默认启用 LangGraph。
- 不改变 `/api/confirm` 恢复语义。

### Phase 8E：稳定后替代手写编排

目标：

- 在 LangGraph 模式测试稳定后，评估是否将默认模式切到 LangGraph。
- 保留 manual 模式作为回滚路径。
- 完善运行文档和故障排查手册。

禁止事项：

- 不在缺少独立 Workflow 测试时切默认模式。
- 不移除关键安全边界。
- 不让 LangGraph 节点直接调用工具。

核心接入原则：

- 不能直接把 `/api/chat` 改成 LangGraph。
- 必须先有独立 Workflow 测试。
- manual 模式必须长期保留，直到 LangGraph 模式稳定。

## 11. 配置开关

设计配置：

```env
SAFEAGENT_WORKFLOW_MODE=manual
```

支持值：

- `manual`
- `langgraph`

默认必须是：

```text
manual
```

配置语义：

- `manual`：继续走当前手写 `/api/chat` 编排。
- `langgraph`：在后续阶段才允许走 LangGraph Workflow。

阶段要求：

- Phase 8A 不实现配置读取。
- Phase 8A 只做设计说明。
- 后续 Phase 8D 才允许在 `/api/chat` 中使用该配置开关。

生产建议：

- 初期生产默认保持 `manual`。
- `langgraph` 应先用于测试环境和灰度环境。
- `langgraph` 失败时，应能通过配置回退到 `manual`。

## 12. 验收标准

LangGraph 接入至少满足以下验收标准：

1. `manual` 模式下现有 170 tests 不受影响。
2. LangGraph Workflow 不绕过 `ActionPlanValidator`。
3. LangGraph Workflow 不绕过 `PolicyService`。
4. LangGraph Workflow 不绕过 `ToolGateway`。
5. `CONFIRM_REQUIRED` 仍只创建 `pending_action`，不直接执行工具。
6. `DENY` 不进入 `ToolGateway`。
7. `HUMAN_REQUIRED` 不自动执行工具。
8. LLM Planner 输出仍必须经过 `LLMOutputGuard` 和 `ActionPlanValidator`。
9. LLM 回复草稿仍必须经过 `LLMResponseGuard`。
10. `/api/confirm` 不重新规划 `ActionPlan`。
11. Workflow 节点必须写 Trace。
12. Workflow State 不保存完整敏感数据。
13. `ToolGateway` 失败后仍由 `FailureHandler` 收口。
14. `FailureHandler` 重试仍必须通过 `ToolGateway`。
15. LangGraph 模式必须有独立测试后，才能接入 `/api/chat`。

补充验收建议：

- `SAFEAGENT_WORKFLOW_MODE=manual` 时，行为与当前 P0 完全一致。
- `SAFEAGENT_WORKFLOW_MODE=langgraph` 时，至少覆盖 8 个 Demo 等价场景。
- LangGraph 节点 Trace 应能还原一次完整 run 的节点路径。
- 任一节点失败时，必须有 `workflow_failed` Trace。

## 13. 非目标范围

Phase 8A 不做：

- 不写 LangGraph 代码。
- 不新增 `langgraph` 依赖。
- 不修改 `/api/chat`。
- 不修改 `/api/confirm`。
- 不接真实 LLM。
- 不接 RAG。
- 不接 MCP。
- 不接前端。
- 不重构 `PolicyService`。
- 不重构 `ToolGateway`。
- 不替换 `PendingActionService`。

Phase 8A 的产出只是一份实现前设计文档。实际代码接入从后续 Phase 8B 开始，并且必须继续遵守现有安全边界。

## 14. 关键风险与工程约束

### 1. manual / langgraph 双轨一致性

`manual` 模式和 `langgraph` 模式不能长期维护两套业务逻辑。LangGraph 节点应尽量复用现有 service 或 service adapter。

节点不重新实现 `PolicyService`、`ToolGateway`、`PendingActionService`、`FailureHandler`。

### 2. Workflow State 字段归属

字段写入归属如下：

- `mode_decision` 只能由 `mode_router_node` 写入。
- `intent_result` 只能由 `intent_node` 写入。
- `action_plan_candidate` 只能由 `planner_node` 写入。
- `action_plan` / `validation_result` 只能由 `action_plan_validator_node` 写入。
- `policy_decision` 只能由 `policy_node` 写入。
- `pending_action_id` 只能由 `pending_action_node` 写入。
- `tool_result` 只能由 `tool_gateway_node` 写入。
- `failure_result` 只能由 `failure_handler_node` 写入。
- `response_draft` 只能由 `response_generation_node` 写入。
- `response_guard_result` 只能由 `llm_response_guard_node` 写入。
- `final_response` 只能由 `response_generation_node` 或 `finish_node` 写入。

节点只读自己需要的字段，只写自己负责产出的字段。

### 3. Trace 与审计日志边界

Trace 是链路观察，不是审计事实凭证。

Policy 裁决事实以后应以 `policy_logs` 或结构化 `PolicyDecision` 记录为准。工具调用事实以 `tool_call_logs` 为准。失败恢复事实以 `failure_logs` 为准。`pending_action` 状态以 `pending_actions` / `pending_action_events` 为准。

### 4. /api/confirm 长期设计

`/api/confirm` 当前不改 LangGraph。

后续如果 Workflow 化，应设计独立 `confirm_workflow`。`confirm_workflow` 不能复用 `/api/chat` 的 `intent_node` 或 `planner_node`。

`confirm_workflow` 只能恢复已保存 `action_plan_json`，重新走 `PolicyService` 复核，再通过 `ToolGateway` 执行。

### 5. 灰度与回滚策略

`SAFEAGENT_WORKFLOW_MODE=manual|langgraph` 只是基础开关。

后续企业落地可以按环境、租户、session 灰度。LangGraph 异常时必须能快速回退 `manual`。

回退不能破坏 `request_id`、`run_id`、`pending_action_id` 的审计连续性。

### 6. 异常分类与超时边界

建议异常分类：

- `PLAN_INVALID`
- `POLICY_DENY`
- `CONFIRM_REQUIRED`
- `HUMAN_REQUIRED`
- `TOOL_FAILED`
- `WORKFLOW_FAILED`

节点失败需要明确分类，不能全部模糊成系统异常。后续每个节点应有超时和失败收口策略。

### 7. 可测试验收断言

后续 Workflow 测试至少覆盖以下断言：

- `DENY` 分支 `tool_call_logs=0`。
- `CONFIRM_REQUIRED` 分支 `pending_actions=1` 且 `tool_call_logs=0`。
- `HUMAN_REQUIRED` 分支不自动调用工具。
- `ALLOW` 分支工具调用必须经过 `ToolGateway`。
- 每个节点至少产生一条 Trace。
- Workflow State 序列化后不包含手机号、完整地址、token、API key、系统 Prompt。
- `/api/confirm` 不重新规划 `ActionPlan`。
