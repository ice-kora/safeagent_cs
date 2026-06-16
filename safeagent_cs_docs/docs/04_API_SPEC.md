# 04 接口文档

## 1. 接口设计原则

- 所有外部请求统一进入 API 层。
- API 层不直接执行业务动作。
- API 层调用 Agent Workflow。
- 每次 HTTP 请求生成 `request_id`。
- 每次 `/api/chat` 或 `/api/confirm` 创建新的 `run_id`。
- 返回结果必须包含 `policy_decision`、`risk_level`、`run_id`。
- 错误要结构化返回，不返回 Python 异常栈。
- 日志和响应中的敏感字段必须脱敏。

ID 定义：

```text
request_id：一次 HTTP 请求
session_id：一次用户会话
run_id：一次 Agent 执行链路
parent_run_id：跨请求恢复或确认时关联的上游 run
trace_node_id：单个节点 Trace 记录
```

## 2. POST /api/chat

### 作用

接收用户消息，执行客服 Agent 主流程。

### 请求

```json
{
  "session_id": "s_001",
  "user_id": "u_1001",
  "channel": "cli",
  "message": "帮我查一下订单 O10086 怎么还没发货"
}
```

### 响应

```json
{
  "request_id": "req_001",
  "session_id": "s_001",
  "run_id": "run_001",
  "parent_run_id": null,
  "intent": "order_query",
  "policy_decision": "ALLOW",
  "risk_level": "L2",
  "final_answer": "你的订单 O10086 当前状态为待发货，预计 24 小时内发出。",
  "ticket_id": null,
  "pending_action_id": null,
  "need_human": false,
  "need_user_confirm": false
}
```

## 3. POST /api/confirm

### 作用

确认 `CONFIRM_REQUIRED` 生成的 pending action，并创建新的 Agent 执行链路继续处理。

确认请求不是继续写入原 run，而是创建新的 `run_id`。

字段关系：

```text
run_id：本次确认请求的新执行链路 ID
parent_run_id：原始触发 CONFIRM_REQUIRED 的 run_id
pending_action_id：待确认动作 ID
```

### 请求

```json
{
  "session_id": "s_001",
  "user_id": "u_1001",
  "pending_action_id": "pa_001",
  "confirm": true
}
```

### 响应

```json
{
  "request_id": "req_002",
  "session_id": "s_001",
  "run_id": "run_002",
  "parent_run_id": "run_001",
  "pending_action_id": "pa_001",
  "policy_decision": "ALLOW",
  "risk_level": "L3",
  "final_answer": "已收到确认，地址修改请求已提交处理。",
  "ticket_id": null,
  "need_human": false,
  "need_user_confirm": false
}
```

### 校验要求

- pending_action_id 存在
- user_id 与 pending action 匹配
- status 为 PENDING 或 CONFIRMED
- 未超过 10 分钟过期时间
- 复核 PolicyService
- 工具调用仍必须经过 ToolGateway
- 全流程写 Trace 和日志

## 4. GET /api/traces/{run_id}

### 作用

查询指定 Agent 执行链路的 Trace。

P0 必须实现该接口。

### 响应

```json
{
  "run_id": "run_001",
  "session_id": "s_001",
  "parent_run_id": null,
  "traces": [
    {
      "trace_node_id": "tn_001",
      "node_name": "classify_intent",
      "input": {
        "message": "帮我查一下订单 O10086 怎么还没发货"
      },
      "output": {
        "intent": "order_query"
      },
      "status": "SUCCESS",
      "created_at": "2026-06-15T12:00:00"
    },
    {
      "trace_node_id": "tn_002",
      "node_name": "policy_check",
      "output": {
        "decision": "ALLOW",
        "risk_level": "L2",
        "reason": "订单属于当前用户"
      },
      "status": "SUCCESS",
      "created_at": "2026-06-15T12:00:01"
    }
  ]
}
```

## 5. GET /api/sessions/{session_id}/runs

### 作用

查询一个 session 下的所有 run。

该接口为 P1 建议实现，P0 不强制。

## 6. GET /api/tickets

### 作用

查询工单列表。

### 响应

```json
{
  "tickets": [
    {
      "id": "T10001",
      "user_id": "u_1001",
      "type": "refund",
      "status": "OPEN",
      "risk_level": "L4",
      "source_run_id": "run_005",
      "pending_action_id": null,
      "description": "用户申请退款，需要人工客服审核"
    }
  ]
}
```

## 7. GET /api/tickets/{ticket_id}

### 作用

查询单个工单详情。

### 响应

```json
{
  "id": "T10001",
  "user_id": "u_1001",
  "type": "refund",
  "status": "OPEN",
  "risk_level": "L4",
  "source_run_id": "run_005",
  "parent_run_id": null,
  "pending_action_id": null,
  "description": "用户申请退款，需要人工客服审核",
  "created_at": "2026-06-15T12:00:00"
}
```

## 8. POST /api/mock/failure-mode

### 作用

设置 Mock Tool 的失败模式，用于演示工具超时、500、空结果等情况。

### 请求

```json
{
  "tool_name": "order_tool.query_order",
  "failure_type": "TOOL_TIMEOUT",
  "enabled": true
}
```

### 响应

```json
{
  "tool_name": "order_tool.query_order",
  "failure_type": "TOOL_TIMEOUT",
  "enabled": true
}
```

## 9. GET /api/health

### 作用

健康检查。

### 响应

```json
{
  "status": "ok",
  "service": "safeagent-cs"
}
```

## 10. 错误响应规范

```json
{
  "error": {
    "code": "POLICY_DENIED",
    "message": "当前动作不允许执行",
    "run_id": "run_001",
    "request_id": "req_001"
  }
}
```

错误响应不得包含内部异常栈、系统 Prompt、API key、token 或未脱敏业务数据。

## 11. 状态枚举

### policy_decision

- ALLOW
- DENY
- CONFIRM_REQUIRED
- HUMAN_REQUIRED

### risk_level

- L0
- L1
- L2
- L3
- L4
- L5

### failure_type

- TOOL_TIMEOUT
- TOOL_5XX
- TOOL_BAD_RESPONSE
- POLICY_DENIED
- RISK_TOO_HIGH
- PLAN_INVALID
- PARAM_MISSING
- RAG_EMPTY
- PROMPT_INJECTION
- UNKNOWN_ACTION
- DUPLICATE_OPERATION

### pending_action status

- PENDING
- CONFIRMED
- EXECUTED
- EXPIRED
- CANCELLED
