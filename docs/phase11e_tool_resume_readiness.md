# Phase 11E-lite Tool Resume Readiness

工具边界恢复的最大风险是重复执行工具。当前 `can_resume_tool_boundary()` 只做协议判断，不恢复、不重试、不调用 `ToolGateway`。

恢复到工具边界至少需要 `action_plan`、`policy_decision=ALLOW` 和 `tool_result`。如果工具已经成功，还必须具备 `tool_call_id` 或 `idempotency_key`，才能在未来安全跳过重复工具执行。缺少这些幂等元数据时，当前协议默认拒绝真实恢复。

如果工具失败，需要 `failure_result` 包含 `attempt_no` 和 `retryable` 等元数据。后续如果 Phase 11D/11E 之后继续推进真实恢复，还需要查询 `tool_call_logs`，确认工具是否已执行、是否允许重试，以及重试仍必须通过 `ToolGateway`。
