# Phase 11D Checkpoint Store / Dry-Run

本阶段新增 `InMemoryCheckpointStore`，用于保存 JSON-safe checkpoint snapshot、按 `checkpoint_id` 查询、按 `run_id` 列表查询，以及执行 resume dry-run 判断。

store 不执行 LangGraph，不调用 `ToolGateway`，不创建 `pending_action`，不修改 run 状态，也不写业务数据库。它只把 `SafeAgentWorkflowState` 转换为 `state_to_json_safe_dict()` 的结果并保存到内存。

dry-run 返回 `ResumeDryRunResult`，其中 `snapshot_summary` 只包含 `request_id`、`run_id`、`final_status`、`route`、`action`、`policy_decision`、`has_tool_result`、`has_pending_action`、`schema_version`。它不会返回完整 message、trace_events、errors、action_plan、tool_result 或 final_response。
