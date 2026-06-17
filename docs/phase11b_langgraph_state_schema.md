# Phase 11B LangGraph State Schema

## 当前状态

SafeAgent-CS 当前真实 LangGraph chat workflow 仍使用 `SafeAgentWorkflowState` 可变对象承载运行态上下文。这个选择可以最大化复用现有节点、服务边界和测试资产，避免在 Phase 11B 阶段把编排迁移扩大成业务重构。

## 为什么需要 JSON-safe snapshot

后续如果启用 checkpoint、resume 或 human interrupt，LangGraph 状态需要能被可靠序列化、持久化和恢复。原始 `SafeAgentWorkflowState` 中可能包含 `ActionPlan`、`PolicyDecision`、`ToolResult`、`FailureHandlingResult` 等对象，不适合直接写入 checkpoint。

## 本阶段不启用 checkpoint 的原因

Phase 11B 只做 readiness，不接入 `MemorySaver`、`SQLiteSaver` 或其他 checkpointer。这样可以先验证状态快照字段、脱敏和 JSON 序列化能力，同时保持当前 `/api/chat` workflow 行为不变。

## Snapshot 字段

`LangGraphCheckpointSnapshot` 包含：`request_id`、`run_id`、`parent_run_id`、`session_id`、`user_id`、`tenant_id`、`message`、`intent_result`、`final_status`、`final_response`、`pending_action_id`、`route`、`action_plan`、`validation_result`、`policy_decision`、`tool_result`、`failure_result`、`errors`、`trace_events`。

## 脱敏要求

Snapshot 不允许明文保存 `api_key`、`token`、`system prompt`、`系统提示词`、`traceback`、`stack trace`、手机号、身份证号、银行卡号、完整地址或详细地址。当前实现先复用 `LoggingService.sanitize_payload`，再补充 checkpoint 专用敏感文本扫描。

## 后续 Phase 11C

Phase 11C 可以在不改变安全边界的前提下，评估是否把 `LangGraphCheckpointSnapshot` 作为真实 checkpointer 的持久化格式。即使启用 checkpoint，`PolicyService`、`ToolGateway`、`PendingActionService`、`FailureHandler` 仍然是安全内核，LangGraph 只负责流程编排与状态传递。
