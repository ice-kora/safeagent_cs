# SafeAgent-CS P0 技术债与后续演进路线

本文档记录 SafeAgent-CS P0 可演示闭环版本的当前边界、已知技术债和后续演进路线。

当前版本定位为受控 Agent 最小闭环系统：它优先保证流程可验证、安全边界清晰、日志和 Trace 可追踪，而不是一次性接入复杂 LLM、LangGraph、真实 RAG 或外部平台。

## 1. 当前 P0 边界

当前 P0 已完成受控 Agent 最小闭环，核心能力包括：

- `/api/chat`：首次用户请求入口。
- `/api/confirm`：二次确认恢复入口。
- `IntentClassifier`：规则意图识别。
- `ActionPlanner`：规则候选 ActionPlan 生成。
- `ActionPlanValidator`：ActionPlan 结构合法性校验。
- `PolicyService`：权限与风险裁决。
- `RepositoryService`：只读 Mock 权限预检。
- `ToolGateway`：工具白名单、工具路由、工具调用日志和脱敏。
- `FailureHandler`：工具失败收口和一次受控重试。
- `PendingActionService`：二次确认动作保存、校验和状态更新。
- `TraceService` / `LoggingService`：Agent 执行链路追踪和结构化脱敏日志。
- Demo + README：8 个标准演示场景和主流程说明。

当前 P0 的关键原则：

- Validator 失败不进入 PolicyService。
- PolicyService 不放行不进入 ToolGateway。
- 工具调用只能经过 ToolGateway。
- `CONFIRM_REQUIRED` 只创建 `pending_action`，不直接执行工具。
- `/api/confirm` 会创建新的 `run_id`，并通过 `parent_run_id` 关联原始 run。

## 2. 已知技术债

1. `pending_actions` 当前是状态表，不是状态流转日志表。

   后续应增加 `pending_action_events`，记录 `old_status`、`new_status`、`run_id`、`user_id`、`event_type`、`reason`、`created_at`。这样可以完整追踪二次确认动作从创建、确认、执行、取消到过期的历史。

2. `ActionPlan.target_id` 当前只支持单资源动作。

   后续如支持批量资源，应升级为 `targets: list[ActionTarget]`。不要使用逗号拼接多个资源 ID，因为字符串拼接会破坏结构化校验、权限判断和审计查询。

3. 当前 `pending_action` 是单步用户确认模型。

   后续如果支持多级审批，应升级为 `approval_flows` / `approval_steps`。例如高风险退款、主管审批、人工复核等场景，不应继续堆叠在单个 `pending_action.status` 字段上。

4. 当前 `FailureHandler` 最多重试一次。

   后续应增加 `RetryPolicy`，支持 `max_attempts`、`retryable_failure_types`、`backoff` 策略。重试仍必须经过 ToolGateway，不能绕过工具调用日志。

5. 当前 Trace / Logs 已能支持主链路追踪，但 `pending_action` 的状态变化历史还不够完整。

   P0 可以查询 run 级链路和工具调用日志，但无法完整还原每次 pending action 状态变化的上下文。该问题应由 `pending_action_events` 补齐。

6. 当前 Rule Mode 可演示，但后续 LLM Mode 必须仍经过 Validator、PolicyService 和 ToolGateway。

   LLM 只能生成候选意图、候选实体和候选 ActionPlan，不能直接调用工具，不能覆盖 PolicyService 的拒绝结论，也不能绕过 ToolGateway。

## 3. 后续演进路线

### P0.1：补充审计能力

- 增加 `pending_action_events`。
- 补充更完整的 pending action 状态流转日志。
- 补充更清晰的 `failure_logs` 查询说明。
- 完善按 `run_id`、`pending_action_id`、`session_id` 的审计查询路径。

### P0.5：LLM Mode

- 增加 `LLMIntentClassifier`。
- 增加 `LLMActionPlanner`。
- 对 LLM 输出做 JSON schema 校验。
- LLM 调用失败、输出非法或结构不可信时，自动降级到 Rule Mode。
- LLM Mode 仍必须经过 Validator / PolicyService / ToolGateway。
- LLMResponseGenerator 只能接收脱敏后的安全摘要，不能接收完整订单、支付信息、系统 Prompt、API key 或内部异常栈。

### P1：LangGraph Workflow

- 用 LangGraph 替代 `/api/chat` 中的手写流程编排。
- LangGraph 节点内部仍复用现有服务。
- LangGraph 只负责流程编排、状态传递、interrupt / resume。
- LangGraph 不替代 PolicyService、ToolGateway、PendingActionService 和审计日志体系。
- `/api/confirm` 的恢复语义仍应保留新的 `run_id` + `parent_run_id` 模型。

### P1+：真实业务接入

- 接入真实 RAG。
- 接入真实订单系统。
- 建设前端控制台。
- 接入 Telegram / Slack / 飞书等外部平台。
- 引入多角色客服权限模型。
- 增加客服后台代客操作场景，区分 `actor_id`、`actor_role`、`subject_customer_user_id`、`resource_owner_id`。

## 4. LangGraph 接入边界

LangGraph 只替代流程编排层，不替代业务安全边界。

接入 LangGraph 后仍然保留：

- `PolicyService`
- `ToolGateway`
- `PendingActionService`
- `RepositoryService`
- `TraceService`
- `tool_call_logs`
- `failure_logs`
- `pending_actions`

推荐边界：

- LangGraph 节点可以调用 `IntentClassifier`、`ActionPlanner`、`ActionPlanValidator`、`PolicyService`、`ToolGateway`、`FailureHandler`、`PendingActionService`。
- LangGraph 不直接访问 Mock Tool。
- LangGraph 不直接修改订单、退款或工单。
- LangGraph 不决定最终权限结论。
- LangGraph 不替代数据库审计日志。

因此，未来迁移到 LangGraph 时，核心变化应集中在 `/api/chat` 的流程编排方式，而不是推翻现有服务边界。现有服务应继续作为确定性、安全可测的业务单元存在。
