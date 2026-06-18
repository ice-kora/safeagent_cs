# SQLite 不支持 MySQL 风格的字段 COMMENT。
# 这里用 SQL 注释维护字段中文说明，方便学习、答辩和后续审计设计对齐。
SCHEMA_SQL = """
-- users：客户/买家最小身份上下文表
CREATE TABLE IF NOT EXISTS users (
    -- id：客户/买家 ID，P0 语义等同 customer_user_id
    id TEXT PRIMARY KEY,
    -- role：角色预留字段，P0 仅作为后续客服权限扩展准备
    role TEXT,
    -- tenant_id：当前客服入口所属商家/租户 ID
    tenant_id TEXT,
    -- status：用户状态，例如 ACTIVE
    status TEXT,
    -- created_at：创建时间
    created_at TEXT,
    -- updated_at：最近更新时间
    updated_at TEXT
);

-- orders：订单权限预检最小上下文表
CREATE TABLE IF NOT EXISTS orders (
    -- id：订单 ID
    id TEXT PRIMARY KEY,
    -- user_id：订单所属客户/买家 ID
    user_id TEXT NOT NULL,
    -- tenant_id：订单所属商家/租户 ID
    tenant_id TEXT NOT NULL,
    -- status：订单状态
    status TEXT,
    -- delivery_status：配送状态
    delivery_status TEXT,
    -- refund_status：退款状态
    refund_status TEXT,
    -- created_at：创建时间
    created_at TEXT,
    -- updated_at：最近更新时间
    updated_at TEXT
);

-- agent_runs：一次 Agent 执行链路记录表
CREATE TABLE IF NOT EXISTS agent_runs (
    -- run_id：一次 Agent 执行链路 ID
    run_id TEXT PRIMARY KEY,
    -- session_id：一次用户会话 ID
    session_id TEXT NOT NULL,
    -- user_id：当前请求用户 ID
    user_id TEXT NOT NULL,
    -- request_id：一次 HTTP 请求 ID
    request_id TEXT NOT NULL,
    -- parent_run_id：父级 run，用于 /api/confirm 等跨请求链路关联
    parent_run_id TEXT,
    -- pending_action_id：待确认动作 ID，仅确认流程需要
    pending_action_id TEXT,
    -- status：RUNNING / SUCCESS / FAILED
    status TEXT NOT NULL,
    -- created_at：创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- updated_at：最近更新时间，finish_run / fail_run 会更新
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- agent_traces：Agent 节点执行轨迹表
CREATE TABLE IF NOT EXISTS agent_traces (
    -- trace_node_id：单个节点 Trace 记录 ID
    trace_node_id TEXT PRIMARY KEY,
    -- run_id：所属 Agent 执行链路
    run_id TEXT NOT NULL,
    -- parent_run_id：跨请求链路的上游 run，可为空
    parent_run_id TEXT,
    -- session_id：所属用户会话
    session_id TEXT NOT NULL,
    -- node_name：工作流节点名称
    node_name TEXT NOT NULL,
    -- input_json：节点输入摘要，必须脱敏
    input_json TEXT NOT NULL,
    -- output_json：节点输出摘要，必须脱敏
    output_json TEXT NOT NULL,
    -- status：SUCCESS / FAILED
    status TEXT NOT NULL,
    -- error_type：节点失败类型，可为空
    error_type TEXT,
    -- created_at：记录创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

-- policy_logs：权限与风险裁决日志表
CREATE TABLE IF NOT EXISTS policy_logs (
    -- id：日志 ID
    id TEXT PRIMARY KEY,
    -- run_id：所属 Agent 执行链路
    run_id TEXT NOT NULL,
    -- session_id：所属用户会话
    session_id TEXT NOT NULL,
    -- user_id：当前请求用户 ID
    user_id TEXT NOT NULL,
    -- role：用户角色
    role TEXT,
    -- tenant_id：租户 ID
    tenant_id TEXT,
    -- action：计划动作
    action TEXT,
    -- target_type：目标资源类型
    target_type TEXT,
    -- target_id：目标资源 ID
    target_id TEXT,
    -- decision：ALLOW / DENY / CONFIRM_REQUIRED / HUMAN_REQUIRED
    decision TEXT NOT NULL,
    -- risk_level：L0-L5 风险等级
    risk_level TEXT NOT NULL,
    -- reason：面向审计的裁决原因，不记录敏感明文
    reason TEXT,
    -- created_at：记录创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- tool_call_logs：工具调用日志表
CREATE TABLE IF NOT EXISTS tool_call_logs (
    -- id：日志 ID
    id TEXT PRIMARY KEY,
    -- tool_call_id：一次物理工具调用 ID，每次真正进入 ToolGateway 都不同
    tool_call_id TEXT,
    -- idempotency_key：逻辑业务动作幂等键，用于后续 retry/resume/duplicate prevention
    idempotency_key TEXT,
    -- action_fingerprint：ActionPlan / 工具上下文的稳定 hash，不保存敏感明文
    action_fingerprint TEXT,
    -- run_id：所属 Agent 执行链路
    run_id TEXT NOT NULL,
    -- session_id：所属用户会话
    session_id TEXT NOT NULL,
    -- tool_name：工具名称
    tool_name TEXT NOT NULL,
    -- attempt_no：同一个 run 内的第几次工具调用尝试
    attempt_no INTEGER NOT NULL,
    -- tool_args_json：工具参数摘要，必须脱敏
    tool_args_json TEXT NOT NULL,
    -- tool_result_summary_json：工具结果摘要，必须脱敏
    tool_result_summary_json TEXT NOT NULL,
    -- status：SUCCESS / FAILED
    status TEXT NOT NULL,
    -- failure_type：工具失败类型，可为空
    failure_type TEXT,
    -- latency_ms：工具调用耗时
    latency_ms INTEGER,
    -- created_at：记录创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- pending_action_events：pending_action 状态流转事件事实表
CREATE TABLE IF NOT EXISTS pending_action_events (
    -- event_id：事件 ID
    event_id TEXT PRIMARY KEY,
    -- pending_action_id：关联待确认动作 ID
    pending_action_id TEXT NOT NULL,
    -- run_id：触发该事件的 run，可为空
    run_id TEXT,
    -- parent_run_id：跨请求父级 run，可为空
    parent_run_id TEXT,
    -- session_id：所属用户会话
    session_id TEXT,
    -- user_id：所属用户
    user_id TEXT,
    -- tenant_id：租户 ID，可为空
    tenant_id TEXT,
    -- event_type：CREATED / CONFIRMED / CANCELLED / EXPIRED / EXECUTED 等
    event_type TEXT NOT NULL,
    -- old_status：状态变化前
    old_status TEXT,
    -- new_status：状态变化后
    new_status TEXT,
    -- reason：事件原因，必须脱敏
    reason TEXT,
    -- metadata_json：事件元数据，必须脱敏且 JSON-safe
    metadata_json TEXT,
    -- created_at：记录创建时间
    created_at TEXT NOT NULL
);

-- failure_logs：失败处理日志表
CREATE TABLE IF NOT EXISTS failure_logs (
    -- id：日志 ID
    id TEXT PRIMARY KEY,
    -- run_id：所属 Agent 执行链路
    run_id TEXT NOT NULL,
    -- session_id：所属用户会话
    session_id TEXT NOT NULL,
    -- failure_type：失败类型
    failure_type TEXT NOT NULL,
    -- source：失败来源，例如 tool_gateway / planner
    source TEXT NOT NULL,
    -- retryable：是否允许重试，0/1 表示 false/true
    retryable INTEGER NOT NULL DEFAULT 0,
    -- retry_count：已重试次数
    retry_count INTEGER NOT NULL DEFAULT 0,
    -- fallback_action：降级动作
    fallback_action TEXT,
    -- final_status：失败处理后的最终状态
    final_status TEXT,
    -- created_at：记录创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- security_logs：安全风险日志表
CREATE TABLE IF NOT EXISTS security_logs (
    -- id：日志 ID
    id TEXT PRIMARY KEY,
    -- run_id：所属 Agent 执行链路
    run_id TEXT NOT NULL,
    -- session_id：所属用户会话
    session_id TEXT NOT NULL,
    -- user_id：当前请求用户 ID
    user_id TEXT,
    -- risk_type：安全风险类型
    risk_type TEXT NOT NULL,
    -- raw_message_summary：原始输入摘要，必须脱敏
    raw_message_summary TEXT,
    -- normalized_message_summary：标准化输入摘要，必须脱敏
    normalized_message_summary TEXT,
    -- decision：安全处理决策
    decision TEXT,
    -- reason：安全处理原因
    reason TEXT,
    -- created_at：记录创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- pending_actions：用户二次确认待执行动作表
CREATE TABLE IF NOT EXISTS pending_actions (
    -- pending_action_id：待确认动作 ID
    pending_action_id TEXT PRIMARY KEY,
    -- session_id：所属用户会话
    session_id TEXT NOT NULL,
    -- source_run_id：触发 CONFIRM_REQUIRED 的原始 run
    source_run_id TEXT NOT NULL,
    -- user_id：待确认动作所属用户
    user_id TEXT NOT NULL,
    -- action_plan_json：待确认 ActionPlan，必须是结构化 JSON
    action_plan_json TEXT NOT NULL,
    -- risk_level：该动作风险等级
    risk_level TEXT NOT NULL,
    -- status：PENDING / CONFIRMED / EXECUTED / EXPIRED / CANCELLED
    status TEXT NOT NULL,
    -- expires_at：默认 10 分钟过期
    expires_at TEXT NOT NULL,
    -- created_at：创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- updated_at：最近更新时间
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- tickets：人工处理工单表
CREATE TABLE IF NOT EXISTS tickets (
    -- id：工单 ID
    id TEXT PRIMARY KEY,
    -- user_id：工单所属用户
    user_id TEXT NOT NULL,
    -- type：工单类型
    type TEXT NOT NULL,
    -- status：OPEN / PROCESSING / CLOSED
    status TEXT NOT NULL,
    -- risk_level：风险等级
    risk_level TEXT NOT NULL,
    -- idempotency_key：工单幂等键，避免重复创建未关闭工单
    idempotency_key TEXT NOT NULL,
    -- source_run_id：创建工单的 run
    source_run_id TEXT,
    -- parent_run_id：跨请求链路上游 run，可为空
    parent_run_id TEXT,
    -- pending_action_id：关联待确认动作，可为空
    pending_action_id TEXT,
    -- description：工单描述，不记录敏感明文
    description TEXT,
    -- created_at：创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- updated_at：最近更新时间
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id
    ON agent_runs(session_id);

CREATE INDEX IF NOT EXISTS idx_users_tenant_id
    ON users(tenant_id);

CREATE INDEX IF NOT EXISTS idx_orders_user_tenant
    ON orders(user_id, tenant_id);

CREATE INDEX IF NOT EXISTS idx_agent_traces_run_id
    ON agent_traces(run_id);

CREATE INDEX IF NOT EXISTS idx_policy_logs_run_id
    ON policy_logs(run_id);

CREATE INDEX IF NOT EXISTS idx_tool_call_logs_run_id
    ON tool_call_logs(run_id);

CREATE INDEX IF NOT EXISTS idx_failure_logs_run_id
    ON failure_logs(run_id);

CREATE INDEX IF NOT EXISTS idx_security_logs_run_id
    ON security_logs(run_id);

CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status
    ON pending_actions(user_id, status);

CREATE INDEX IF NOT EXISTS idx_pending_action_events_pending_action_id
    ON pending_action_events(pending_action_id);

CREATE INDEX IF NOT EXISTS idx_pending_action_events_run_id
    ON pending_action_events(run_id);

CREATE INDEX IF NOT EXISTS idx_tickets_user_status
    ON tickets(user_id, status);

CREATE INDEX IF NOT EXISTS idx_tickets_idempotency_status
    ON tickets(idempotency_key, status);
"""
