# 03 Agent 流程与权限策略设计文档

## 1. 设计目标

本项目的核心不是让 LLM 直接回答客服问题，而是建立一个受控 Agent 流程。

核心目标：

- Rule Mode 负责 P0 稳定意图识别和 ActionPlan 生成。
- LLM Mode 仅作为 P0.5 可选增强，负责候选理解和候选规划。
- ActionPlanValidator 负责候选计划结构校验。
- PolicyService 负责权限和风险判断。
- ToolGateway 负责工具执行控制。
- FailureHandler 负责失败处理和降级。
- TraceLog 负责全链路审计。

## 2. 核心原则

```text
LLM 不可信。
ActionPlan 不可信。
ActionPlanValidator 只证明计划结构合法。
PolicyDecision 可信。
ToolGateway 是唯一工具入口。
未知动作默认拒绝。
高风险动作默认转人工。
```

## 3. Agent 主流程

```text
START
  ↓
normalize_message
  ↓
input_guard
  ↓
classify_intent
  ↓
plan_action
  ↓
validate_action_plan
  ↓
policy_check
  ├── DENY → safe_refusal
  ├── CONFIRM_REQUIRED → save_pending_action → ask_user_confirmation
  ├── HUMAN_REQUIRED → create_ticket
  └── ALLOW → tool_gateway
  ↓
handle_tool_result
  ├── success → generate_response
  └── failed → failure_handler
  ↓
save_trace
  ↓
END
```

## 4. State 定义

```python
from typing import TypedDict, Literal, Optional, Any

class CustomerAgentState(TypedDict):
    request_id: str
    session_id: str
    run_id: str
    parent_run_id: Optional[str]
    user_id: str
    role: str
    tenant_id: str
    channel: str

    raw_message: str
    normalized_message: str

    intent: Optional[str]
    entities: dict[str, Any]

    action_plan: Optional[dict]
    action_plan_valid: bool
    action_plan_error: Optional[str]
    action_type: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]

    risk_level: Literal["L0", "L1", "L2", "L3", "L4", "L5"]
    policy_decision: Literal[
        "ALLOW",
        "DENY",
        "CONFIRM_REQUIRED",
        "HUMAN_REQUIRED"
    ]
    policy_reason: str

    tool_name: Optional[str]
    tool_args: dict[str, Any]
    tool_result: Optional[dict]
    tool_error: Optional[dict]

    retry_count: int
    failure_type: Optional[str]
    fallback_action: Optional[str]

    final_answer: str
    ticket_id: Optional[str]
    pending_action_id: Optional[str]
    need_human: bool
    need_user_confirm: bool

    trace: list[dict]
```

ID 口径：

```text
request_id：一次 HTTP 请求
session_id：一次用户会话
run_id：一次 Agent 执行链路
parent_run_id：跨请求恢复或确认时关联的上游 run
trace_node_id：单个节点 Trace 记录
```

## 5. ActionPlan 结构

LLM 或规则 Planner 只能生成 ActionPlan，不允许直接执行。

```json
{
  "intent": "order_query",
  "action": "query_order",
  "target_type": "order",
  "target_id": "O10086",
  "tool_name": "order_tool.query_order",
  "tool_args": {
    "order_id": "O10086"
  },
  "reason": "用户询问订单发货状态"
}
```

## 6. ActionPlanValidator

ActionPlanValidator 负责判断候选 ActionPlan 是否“像一个合法计划”。

它负责：

- 校验 LLM / Planner 输出是否为合法 JSON
- 校验 action 是否在允许动作集合中
- 校验 target_type 是否合法
- 校验 tool_name 是否在候选工具集合中
- 校验必要参数是否存在
- 校验是否存在明显危险动作
- 校验失败时返回 PLAN_INVALID 或 UNKNOWN_ACTION

它不负责：

- 判断订单是否属于当前用户
- 判断租户是否一致
- 判断是否允许查询该订单
- 判断是否需要转人工
- 判断是否允许修改业务状态

LLM 输出不合法时：

```text
第一次尝试修复
修复失败则降级到 RuleBasedActionPlanner
仍失败则追问用户或转人工
```

## 7. PolicyDecision 结构

```json
{
  "decision": "ALLOW",
  "risk_level": "L2",
  "reason": "订单属于当前用户，允许查询本人订单"
}
```

可选 decision：

- ALLOW
- DENY
- CONFIRM_REQUIRED
- HUMAN_REQUIRED

## 8. 风险等级

| 等级 | 场景 | 决策 |
|---|---|---|
| L0 | 问候、闲聊 | 直接回答 |
| L1 | 查询公开政策 | P0 静态知识库 / KnowledgeTool 回答 |
| L2 | 查询本人订单 | 校验后允许 |
| L3 | 修改地址、取消订单 | 用户二次确认 |
| L4 | 退款、投诉升级 | 转人工 |
| L5 | 越权、攻击、系统操作 | 拒绝 |

## 9. PolicyService 规则

PolicyService 负责判断计划“当前用户能不能做、风险多高”。

P0 阶段明确为“客户自助客服入口”，不是“客服后台代客操作入口”。

```text
customer_user_id：当前登录客户 ID，不是客服人员 ID。
merchant_tenant_id：订单所属商家/租户 ID。
session_tenant_id：当前客服入口所属商家/租户 ID。
support_agent_id / actor_id：客服人员 ID，P0 暂不实现。
actor_role：客服角色，例如 support_agent / supervisor / admin，P0 暂不实现。
客户不是商家；商家是租户；客服是操作人员。
订单同时关联 customer_user_id 和 merchant_tenant_id。
当前 PolicyService 实现客户本人资源归属校验。
目标是防止 A 客户访问 B 客户订单。
```

P1 如果支持客服后台代客操作，需要引入：

```text
actor_id
actor_role
subject_customer_user_id
resource_owner_id
```

届时 PolicyService 需要同时判断：

```text
资源归属权限
客服角色操作权限
```

它可以读取 RepositoryService 的只读权限上下文：

```text
order_id
user_id
tenant_id
order_status
delivery_status
refund_status
```

它不能：

```text
修改订单
创建工单
执行退款
调用业务工具
返回敏感字段
```

### 9.1 query_policy

- 公开政策查询
- risk = L1
- decision = ALLOW

### 9.2 query_order

允许条件：

- 订单存在
- 订单 user_id 等于当前 user_id
- tenant_id 一致

否则：

- decision = DENY
- risk = L5

### 9.3 change_address

允许前置条件：

- 订单存在
- 订单属于当前用户
- 订单未发货

决策：

- decision = CONFIRM_REQUIRED
- risk = L3
- 保存 ActionPlan 到 pending_actions
- 返回 pending_action_id

### 9.4 request_refund

决策：

- decision = HUMAN_REQUIRED
- risk = L4

禁止 AI 自动退款。

### 9.5 complaint

决策：

- decision = HUMAN_REQUIRED
- risk = L4

### 9.6 export_user_data

决策：

- decision = DENY
- risk = L5

### 9.7 modify_permission

决策：

- decision = DENY
- risk = L5

### 9.8 unknown_action

决策：

- decision = DENY
- risk = L5

## 10. RepositoryService 规则

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

不要返回完整手机号、完整地址、支付信息或完整订单详情。

## 11. ToolGateway 规则

ToolGateway 是唯一工具调用入口。

必须检查：

1. policy_decision 是否为 ALLOW。
2. tool_name 是否在白名单。
3. tool_args 是否符合 schema。
4. target_id 是否与用户权限匹配。
5. 工具结果是否需要脱敏。
6. 是否记录 tool_call_log。

ToolGateway 每次只执行一次工具调用。重试由 FailureHandler 决定。

`tool_call_logs` 需要记录：

```text
run_id
tool_name
attempt_no
status
failure_type
latency_ms
created_at
```

## 12. HITL 策略

HITL 包括两类：

### 12.1 用户确认

适用于 L3：

- 修改地址
- 取消订单
- 修改联系方式

处理：

- PolicyService 返回 CONFIRM_REQUIRED
- PendingActionService 将 ActionPlan 保存到 SQLite
- 返回 pending_action_id
- 用户调用 `POST /api/confirm`
- `/api/confirm` 创建新的 run_id，并设置 parent_run_id 为原始 run_id
- 校验用户、状态和 10 分钟过期时间
- 复核 Policy
- 调用 ToolGateway
- 记录 Trace

### 12.2 人工接管

适用于 L4：

- 退款
- 投诉
- 赔偿
- 法务风险
- 高金额动作

处理：

- 创建工单
- 标记风险等级
- 返回人工处理说明

## 13. LLM Mode 边界

真实 LLM 可以参与：

- 意图识别
- 实体提取
- ActionPlan 生成
- 复杂用户表达拆解
- 最终回复润色

真实 LLM 不可以：

- 决定是否允许访问数据
- 决定是否执行退款
- 决定是否修改地址
- 绕过 PolicyService
- 绕过 ToolGateway
- 直接调用业务工具
- 修改最终 risk_level
- 覆盖 PolicyService 的 DENY / HUMAN_REQUIRED 结论

LLMResponseGenerator 只能接收脱敏后的安全摘要：

```text
intent
policy_decision
risk_level
safe_tool_summary
safe_failure_summary
ticket_id
public_reason
sources
```

禁止传入完整手机号、完整地址、支付信息、完整订单对象、内部异常栈、系统 Prompt、API key、token、未脱敏工具结果或完整策略细节。

## 14. 拒绝策略

拒绝时不能只说“不行”。

应返回：

- 安全说明
- 可替代路径
- 是否创建工单

示例：

```text
抱歉，我不能查询不属于你的订单信息。为了保护用户隐私，我只能处理当前账号下的订单。如果你认为订单归属有误，可以提交工单由人工客服核验。
```

## 15. Trace 记录点

每个节点必须记录：

- run_id
- parent_run_id
- node_name
- input summary
- output summary
- decision
- error_type
- timestamp

重点记录：

- input_guard
- classify_intent
- plan_action
- validate_action_plan
- policy_check
- save_pending_action
- tool_gateway
- failure_handler
- create_ticket
- generate_response
