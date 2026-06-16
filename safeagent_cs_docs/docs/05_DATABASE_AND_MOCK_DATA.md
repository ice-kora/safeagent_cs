# 05 数据库与 Mock 数据文档

## 1. 设计原则

本项目不接真实业务系统，但需要模拟真实企业系统的数据结构。

原因：

- 让 Agent 有业务上下文
- 支撑权限校验
- 支撑工单流转
- 支撑 Trace 审计
- 支撑 pending action 二次确认
- 支撑失败场景模拟
- 让代码结构接近企业项目

## 2. 推荐存储方式

P0：

- SQLite
- JSON Mock 数据

P1：

- SQLAlchemy ORM
- 可选 Alembic

## 3. 表设计

### 3.1 users

用户表。

P0 中该表模拟客户自助客服入口的客户身份。客户不是商家，商家是租户。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 客户 ID，语义为 customer_user_id |
| name | string | 用户名 |
| role | string | user / agent / staff / supervisor / admin，P0 暂不参与复杂授权 |
| tenant_id | string | 当前客服入口所属商家/租户 ID，语义为 session_tenant_id |
| status | string | ACTIVE / DISABLED |

示例：

```json
{
  "id": "u_1001",
  "name": "张三",
  "role": "user",
  "tenant_id": "t_001",
  "status": "ACTIVE"
}
```

### 3.2 agent_runs

Agent 执行链路记录表。

| 字段 | 类型 | 说明 |
|---|---|---|
| run_id | string | 一次 Agent 执行链路 ID |
| session_id | string | 一次用户会话 ID |
| user_id | string | 当前发起咨询的客户 ID，语义为 customer_user_id |
| request_id | string | 一次 HTTP 请求 ID |
| parent_run_id | string | 父级 run，用于 `/api/confirm` 等跨请求链路关联 |
| pending_action_id | string | 待确认动作 ID，可为空 |
| status | string | RUNNING / SUCCESS / FAILED |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 3.3 orders

订单表。

订单同时关联客户和商家：`user_id` 表示订单所属客户，`tenant_id` 表示订单所属商家/租户。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 订单 ID |
| user_id | string | 订单所属客户 ID，语义为 customer_user_id |
| tenant_id | string | 订单所属商家/租户 ID，语义为 merchant_tenant_id |
| status | string | CREATED / PAID / SHIPPED / COMPLETED / REFUNDED |
| amount | number | 金额 |
| address_masked | string | 脱敏地址 |
| delivery_status | string | 物流状态 |
| refund_status | string | 退款状态 |

示例：

```json
{
  "id": "O10086",
  "user_id": "u_1001",
  "tenant_id": "t_001",
  "status": "PAID",
  "amount": 199.0,
  "address_masked": "河南省郑州市***",
  "delivery_status": "待发货",
  "refund_status": "NONE"
}
```

### 3.4 tickets

工单表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 工单 ID |
| user_id | string | 客户 ID，语义为 customer_user_id |
| type | string | refund / complaint / order / address / unknown |
| status | string | OPEN / PROCESSING / CLOSED |
| risk_level | string | L0-L5 |
| idempotency_key | string | 幂等键 |
| source_run_id | string | 创建工单的 run_id |
| parent_run_id | string | 可选，上游 run_id |
| pending_action_id | string | 可选，关联确认动作 |
| description | string | 工单描述 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 3.5 agent_traces

Agent 执行轨迹表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | trace_node_id |
| run_id | string | Agent 执行链路 ID |
| parent_run_id | string | 可选，上游 run_id |
| session_id | string | 会话 ID |
| node_name | string | 节点名称 |
| input_json | json | 节点输入 |
| output_json | json | 节点输出 |
| status | string | SUCCESS / FAILED |
| error_type | string | 失败类型 |
| created_at | string | 时间 |

### 3.6 policy_logs

策略决策日志表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 日志 ID |
| run_id | string | Agent 执行链路 ID |
| session_id | string | 会话 ID |
| user_id | string | 客户 ID，语义为 customer_user_id |
| role | string | 用户角色 |
| tenant_id | string | 当前客服入口所属商家/租户 ID，语义为 session_tenant_id |
| action | string | 动作 |
| target_type | string | 目标类型 |
| target_id | string | 目标 ID |
| decision | string | ALLOW / DENY / CONFIRM_REQUIRED / HUMAN_REQUIRED |
| risk_level | string | L0-L5 |
| reason | string | 原因 |
| created_at | string | 时间 |

### 3.7 tool_call_logs

工具调用日志表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 日志 ID |
| run_id | string | Agent 执行链路 ID |
| session_id | string | 会话 ID |
| tool_name | string | 工具名称 |
| attempt_no | integer | 当前 run 内工具调用尝试次数 |
| tool_args_json | json | 工具参数 |
| tool_result_summary_json | json | 脱敏后的工具结果摘要 |
| status | string | SUCCESS / FAILED |
| failure_type | string | 失败类型 |
| latency_ms | integer | 调用耗时 |
| created_at | string | 时间 |

示例：

```text
run_003, order_tool.query_order, attempt_no=1, FAILED, TOOL_TIMEOUT
run_003, order_tool.query_order, attempt_no=2, FAILED, TOOL_TIMEOUT
```

### 3.8 failure_scenarios

失败场景配置。

| 字段 | 类型 | 说明 |
|---|---|---|
| tool_name | string | 工具名称 |
| failure_type | string | 失败类型 |
| enabled | bool | 是否启用 |
| retryable | bool | 是否可重试 |

示例：

```json
{
  "tool_name": "order_tool.query_order",
  "failure_type": "TOOL_TIMEOUT",
  "enabled": true,
  "retryable": true
}
```

### 3.9 pending_actions

待确认动作表。

P0 使用 SQLite 存储，不使用纯内存。

| 字段 | 类型 | 说明 |
|---|---|---|
| pending_action_id | string | 待确认动作 ID |
| session_id | string | 会话 ID |
| source_run_id | string | 触发 CONFIRM_REQUIRED 的 run_id |
| user_id | string | 客户 ID，语义为 customer_user_id |
| action_plan_json | json | 待确认的 ActionPlan |
| risk_level | string | 风险等级 |
| status | string | PENDING / CONFIRMED / EXECUTED / EXPIRED / CANCELLED |
| expires_at | string | 过期时间 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

默认过期时间：

```text
10 分钟
```

### 3.10 failure_logs

失败处理日志表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 日志 ID |
| run_id | string | Agent 执行链路 ID |
| session_id | string | 会话 ID |
| failure_type | string | 失败类型 |
| source | string | 失败来源 |
| retryable | bool | 是否可重试 |
| retry_count | integer | 已重试次数 |
| fallback_action | string | 降级动作 |
| final_status | string | 最终状态 |
| created_at | string | 时间 |

### 3.11 security_logs

安全风险日志表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 日志 ID |
| run_id | string | Agent 执行链路 ID |
| session_id | string | 会话 ID |
| user_id | string | 客户 ID，语义为 customer_user_id |
| risk_type | string | 风险类型 |
| raw_message_summary | string | 脱敏后的原始输入摘要 |
| normalized_message_summary | string | 脱敏后的标准化输入摘要 |
| decision | string | 处理决策 |
| reason | string | 原因 |
| created_at | string | 时间 |

## 4. Mock Tool 数据

### mock_users.json

至少准备：

- u_1001：普通用户
- u_1002：另一个普通用户
- staff_001：人工客服
- supervisor_001：客服主管

### mock_orders.json

至少准备：

- O10086：属于 u_1001，待发货
- O10087：属于 u_1002，已发货
- O10088：属于 u_1001，已完成
- O10089：属于 u_1001，已退款

### mock_knowledge_docs

至少准备：

- return_policy.md
- refund_policy.md
- invoice_policy.md
- complaint_policy.md
- address_change_policy.md

## 5. 数据脱敏规则

返回给 LLM、用户和日志的数据必须脱敏：

- 手机号：138****1234
- 地址：省市 + ***
- 身份证：不返回
- 支付信息：不返回
- 其他用户信息：不返回
- API key、token、系统 Prompt、内部异常栈：不记录

## 6. 幂等规则

以下动作必须防止重复执行：

- 创建退款工单
- 创建投诉工单
- 修改地址
- 取消订单

P0 使用：

```text
idempotency_key = user_id + action + target_type + target_id
```

只拦截未关闭工单：

```text
OPEN
PROCESSING
```

如果工单状态为 `CLOSED`，允许再次创建新工单。

## 7. RepositoryService 只读上下文

RepositoryService 只暴露专用只读方法，不暴露完整订单对象。

建议方法：

```text
get_order_auth_context(order_id)
get_user_context(user_id)
get_open_ticket_by_idempotency_key(idempotency_key)
```

`get_order_auth_context(order_id)` 只返回：

```json
{
  "order_id": "O10086",
  "user_id": "u_1001",
  "tenant_id": "t_001",
  "order_status": "PAID",
  "delivery_status": "待发货",
  "refund_status": "NONE"
}
```

其中：

```text
user_id：订单所属客户 ID，语义为 customer_user_id。
tenant_id：订单所属商家/租户 ID，语义为 merchant_tenant_id。
```

## 8. 索引设计

P0 阶段至少创建以下索引，保证后续按 run、session、用户状态查询时不需要全表扫描：

```sql
CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id
    ON agent_runs(session_id);

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

CREATE INDEX IF NOT EXISTS idx_tickets_user_status
    ON tickets(user_id, status);

CREATE INDEX IF NOT EXISTS idx_tickets_idempotency_status
    ON tickets(idempotency_key, status);
```
