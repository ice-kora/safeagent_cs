# Phase 11 Resume Matrix

当前矩阵策略：

- `SAFE` 节点：允许 checkpoint，允许 dry-run，真实 resume 暂不启用。
- `SIDE_EFFECT` 节点：允许谨慎 checkpoint，允许 dry-run 判断，真实 resume 禁止。
- `TERMINAL` 节点：允许 checkpoint，允许 dry-run close 状态，真实 resume 暂不启用。
- `UNSAFE_TO_RESUME` 节点：不允许 checkpoint，不允许 dry-run，不允许真实 resume。

覆盖节点包括：`workflow_start_node`、`intent_node`、`planner_node`、`llm_output_guard_node`、`action_plan_validator_node`、`policy_node`、`route_by_policy_node`、`tool_gateway_node`、`pending_action_node`、`human_required_node`、`deny_node`、`failure_handler_node`、`response_generation_node`、`llm_response_guard_node`、`finish_node`、`unknown_node`。

真实 resume 当前全部关闭。后续只有在补齐工具幂等、pending action 状态事实来源、attempt 元数据、schema version 迁移和审计日志后，才能考虑打开部分节点的真实恢复。
