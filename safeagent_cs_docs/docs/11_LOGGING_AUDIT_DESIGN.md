# 11 日志与审计设计文档

## 1. 设计目标

本项目当前阶段不实现完整审计平台，但必须具备日志基础，为后续审计能力预留结构。

当前阶段目标：

- 有运行日志
- 有 Agent Trace
- 有 Policy 决策日志
- 有 Tool 调用日志
- 有失败日志
- 日志结构化
- 日志可查询
- 后续可升级为审计记录

## 2. 日志与审计的区别

### 2.1 普通日志 Logging

普通日志主要用于开发、调试和运行排障。

关注：

- 系统发生了什么
- 是否报错
- 哪个模块失败
- 调用耗时
- 异常原因

示例：

```text
order_tool.query_order timeout after 3s
```

### 2.2 Trace

Trace 用于记录一次 Agent 请求的完整执行链路。

关注：

- 用户输入是什么
- 经过哪些节点
- 每个节点输出什么
- 最后为什么这样回答

示例：

```text
input_guard -> classify_intent -> plan_action -> policy_check -> tool_gateway -> generate_response
```

### 2.3 Audit Log 审计日志

审计日志用于安全、合规、追责和复盘。

关注：

- 谁在什么时候请求了什么
- Agent 计划执行什么动作
- 策略层是否允许
- 工具是否被调用
- 是否访问了敏感数据
- 是否发生越权请求
- 谁批准了高风险动作
- 最终产生了什么业务影响

审计日志要求更高：

- 结构化
- 可追踪
- 可检索
- 尽量 append-only
- 不随意修改
- 能支撑后续追责

## 3. 当前阶段必须实现的日志类型

### 3.1 application.log

系统运行日志。

用途：

- 开发调试
- 服务启动
- API 请求
- 异常排查

建议路径：

```text
logs/application.log
```

### 3.2 agent_traces

Agent 执行轨迹。

记录每个节点输入输出。

字段：

```text
id
run_id
parent_run_id
session_id
node_name
input_json
output_json
status
error_type
created_at
```

### 3.3 policy_logs

权限与风险决策日志。

字段：

```text
id
run_id
session_id
user_id
role
tenant_id
action
target_type
target_id
decision
risk_level
reason
created_at
```

### 3.4 tool_call_logs

工具调用日志。

字段：

```text
id
run_id
session_id
tool_name
attempt_no
tool_args_json
tool_result_summary_json
status
failure_type
latency_ms
created_at
```

注意：

- 不记录完整敏感数据
- 工具结果需要脱敏
- 大字段只记录 summary

### 3.5 security_logs

安全风险日志。

记录：

- Prompt Injection
- 越权访问
- 敏感信息请求
- 未知工具请求
- 权限绕过尝试
- 系统 Prompt 请求

字段：

```text
id
run_id
session_id
user_id
risk_type
raw_message_summary
normalized_message_summary
decision
reason
created_at
```

### 3.6 failure_logs

失败处理日志。

记录：

- TOOL_TIMEOUT
- TOOL_5XX
- TOOL_BAD_RESPONSE
- PLAN_INVALID
- PARAM_MISSING
- RAG_EMPTY
- UNKNOWN_ACTION
- DUPLICATE_OPERATION

字段：

```text
id
run_id
session_id
failure_type
source
retryable
retry_count
fallback_action
final_status
created_at
```

## 4. 当前阶段日志设计原则

### 4.1 不只 print

禁止只使用 print 作为日志。

必须使用 Python logging 或封装 LoggingService。

### 4.2 结构化优先

日志内容尽量结构化。

推荐：

```json
{
  "event": "policy_decision",
  "session_id": "s_001",
  "user_id": "u_1001",
  "action": "query_order",
  "target_id": "O10086",
  "decision": "ALLOW",
  "risk_level": "L2"
}
```

### 4.3 每次请求必须有 run_id

每个 `/api/chat` 和 `/api/confirm` 请求必须生成或携带：

```text
request_id
session_id
run_id
```

推荐：

- session_id：一次对话会话
- run_id：一次 Agent 执行链路
- request_id：一次 HTTP 请求

`/api/confirm` 创建新的 `run_id`，并使用 `parent_run_id` 关联原始触发 `CONFIRM_REQUIRED` 的 run。

工具重试仍属于同一个 `run_id`，只通过 `attempt_no` 区分，不创建新的 `run_id`。

### 4.4 敏感数据不落日志

禁止在日志中记录：

- 完整手机号
- 完整地址
- 身份证
- 支付信息
- access token
- API key
- token
- 系统 Prompt
- 内部异常栈
- 完整用户隐私信息

### 4.5 关键决策必须落库

以下必须写入数据库或 JSONL：

- PolicyDecision
- ToolCall
- ToolError
- SecurityRisk
- HumanRequired
- ConfirmRequired
- TicketCreated

## 5. LoggingService 设计

建议新增：

```text
app/services/logging_service.py
```

职责：

- 写 application log
- 生成 request_id / run_id
- 提供结构化日志方法
- 屏蔽敏感字段
- 统一日志格式

示例方法：

```python
class LoggingService:
    def info(self, event: str, payload: dict) -> None:
        pass

    def warning(self, event: str, payload: dict) -> None:
        pass

    def error(self, event: str, payload: dict) -> None:
        pass

    def security(self, event: str, payload: dict) -> None:
        pass
```

## 6. TraceService 与 AuditService 的关系

当前阶段：

```text
TraceService = 记录 Agent 执行链路
LoggingService = 记录系统运行事件
PolicyLog / ToolCallLog / SecurityLog = 审计雏形
```

后续阶段可升级：

```text
AuditService = 汇总 policy_logs + tool_call_logs + security_logs + failure_logs
```

## 7. 后续审计能力演进

### 阶段 1：日志基础

当前必须完成：

- application.log
- agent_traces
- policy_logs
- tool_call_logs
- failure_logs
- security_logs

### 阶段 2：审计查询

后续可增加：

```text
GET /api/audit/events
GET /api/audit/security
GET /api/audit/policy-decisions
GET /api/audit/tool-calls
```

### 阶段 3：审计报表

后续可增加：

- 越权请求次数
- 高风险转人工次数
- 工具失败次数
- Policy DENY 分布
- Prompt Injection 样本
- Top risky users
- Top failed tools

### 阶段 4：不可篡改审计

后续可考虑：

- append-only 日志
- 日志 hash chain
- 操作签名
- 外部日志系统
- ELK / Loki / OpenTelemetry

## 8. 当前阶段 API 建议

P0 至少保留：

```text
GET /api/traces/{run_id}
```

P1 可增加：

```text
GET /api/sessions/{session_id}/runs
GET /api/logs/security
GET /api/logs/failures
GET /api/logs/policies
GET /api/logs/tools
```

## 9. Codex 实现要求

Codex 必须实现：

1. `app/services/logging_service.py`
2. application.log 文件输出
3. 每个 `/api/chat` 和 `/api/confirm` 生成新的 run_id
4. PolicyService 写 policy_logs
5. ToolGateway 写 tool_call_logs
6. FailureHandler 写 failure_logs
7. InputGuard 写 security_logs
8. TraceService 写 agent_traces
9. 日志脱敏
10. 测试至少覆盖一次 security_log 和一次 failure_log

## 10. 验收标准

当前阶段通过标准：

- 运行后存在 `logs/application.log`
- `/api/chat` 和 `/api/confirm` 每次请求有 run_id
- 查询本人订单有 policy_log 和 tool_call_log
- 查询他人订单有 policy_log 和 security_log
- 工具超时有 failure_log
- Trace 能查到完整节点链路
- 日志中没有完整手机号、完整地址、token、系统 Prompt
