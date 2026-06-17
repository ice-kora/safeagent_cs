# Phase 11C Checkpoint / Resume Protocol

## 为什么不能直接启用 checkpoint

SafeAgent-CS 的 chat workflow 已经可以使用真实 LangGraph 编排，但当前状态恢复协议尚未完成。如果直接启用 checkpoint，系统可能从错误节点恢复，导致重复工具调用、重复创建 `pending_action`、绕过策略复核，或把不完整状态继续向后传递。

## 最大风险：重复工具调用

`tool_gateway_node` 是最关键的副作用边界。只要不能明确工具是否已经执行、执行结果是什么、对应 `tool_call_id` 或幂等键是什么，就不能从该节点直接 resume。否则一次用户请求可能触发多次业务工具调用。

## 节点风险分类

`SAFE` 节点只做确定性分类、计划、校验、策略读取、路由或回复生成。`SIDE_EFFECT` 节点会写入业务状态、工具日志、失败日志或 pending action。`TERMINAL` 节点关闭 run 生命周期。未知节点统一归为 `UNSAFE_TO_RESUME`。

## 可恢复节点与不可恢复节点

`workflow_start_node`、`intent_node`、`planner_node`、`llm_output_guard_node`、`action_plan_validator_node`、`policy_node`、`route_by_policy_node`、`human_required_node`、`deny_node`、`response_generation_node`、`llm_response_guard_node` 在满足前置字段时可以恢复。`tool_gateway_node`、`pending_action_node`、`failure_handler_node` 当前默认不允许直接恢复。

## pending_action 恢复边界

如果 `pending_action_node` 已创建 pending action，但 snapshot 中没有 `pending_action_id`，不能继续恢复执行。后续如果支持恢复，需要以 `pending_action_id` 为事实来源，确认其状态仍为 `PENDING`，并保证不会重复创建。

## ToolGateway 幂等要求

后续 Phase 11D 如果允许恢复工具调用，必须记录 `tool_call_id`、`attempt_no`、幂等键、工具执行结果和失败类型。恢复前需要查询 `tool_call_logs`，判断是否已经完成、是否允许重试，以及重试是否仍必须通过 `ToolGateway`。

## schema_version 策略

当前 checkpoint snapshot 版本为 `checkpoint.snapshot.v1`。缺少版本或未知版本必须拒绝恢复。未来版本升级需要提供迁移策略，不能让恢复流程模糊消费多个不兼容 schema。

## Phase 11D 需要补充的能力

Phase 11D 如果接入真实 checkpointer，需要补充 snapshot 反序列化、恢复节点白名单、工具调用幂等查询、pending action 状态校验、失败重试 attempt 元数据、run 生命周期恢复策略，以及对应的审计日志。
