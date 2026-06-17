# Phase 11F-lite PendingAction Resume Readiness

pending action 边界恢复不能重复创建 `pending_action`。当前 `can_resume_pending_boundary()` 只根据 snapshot 判断，不执行 `/api/confirm`，不创建 pending action，也不查询数据库。

恢复到等待确认状态需要 `policy_decision=CONFIRM_REQUIRED`、`action_plan` 和 `pending_action_id`。如果缺少 `pending_action_id`，说明无法判断 pending action 是否已经创建，直接恢复可能重复创建，因此必须拒绝。

后续如果启用真实恢复，应以数据库中的 `pending_actions` 或未来的 `pending_action_events` 作为事实来源，确认状态仍可等待用户确认。
