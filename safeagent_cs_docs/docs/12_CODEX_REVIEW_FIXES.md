# 12 Codex Review 修正文档

## 1. 修正背景

本文件是早期文档的最终修正口径。若旧文档与本文冲突，以本文为准。

重点修正：

1. 日志与审计基础。
2. 订单权限校验来源。
3. 二次确认恢复执行机制。
4. P0/P0.5/P1 边界。
5. Rule Mode / LLM Mode 双模式。
6. ActionPlanValidator 职责。
7. run_id / trace 命名。
8. 工单幂等规则。
9. 失败重试边界。
10. LLMResponseGenerator 数据边界。

## 2. 日志与审计基础

当前阶段不需要完整审计后台，但必须有日志基础。

必须实现或预留：

```text
app/services/logging_service.py
logs/application.log
agent_traces
policy_logs
tool_call_logs
failure_logs
security_logs
```

要求：

- 每次 `/api/chat` 和 `/api/confirm` 有新的 `run_id`。
- 每次关键节点写 trace。
- PolicyService 写 policy_log。
- ToolGateway 写 tool_call_log。
- FailureHandler 写 failure_log。
- InputGuard 写 security_log。
- 日志必须脱敏。
- 不允许只用 print。

禁止记录：

```text
完整手机号
完整地址
身份证
支付信息
API key
token
系统 Prompt
内部异常栈
```

## 3. 订单权限校验来源

PolicyService 可以读取只读 Mock Repository / RepositoryService 做权限预检。

P0 阶段是客户自助客服入口，PolicyService 使用 `customer_user_id` 表示当前登录客户 ID。

```text
customer_user_id 不是客服人员 ID。
customer_user_id 是当前发起咨询的客户/买家 ID。
merchant_tenant_id 是订单所属商家/租户 ID。
session_tenant_id 是当前客服入口所属商家/租户 ID。
support_agent_id / actor_id 是客服人员 ID，P0 暂不实现。
actor_role 是客服角色，例如 support_agent / supervisor / admin，P0 暂不实现。
客户不是商家；商家是租户；客服是操作人员。
订单同时关联 customer_user_id 和 merchant_tenant_id。
当前实现只做客户本人资源归属校验。
目标是防止 A 客户访问 B 客户订单。
```

P1 如果支持客服后台代客操作，需要引入：

```text
actor_id
actor_role
subject_customer_user_id
resource_owner_id
```

届时 PolicyService 需要同时判断“资源归属权限”和“客服角色操作权限”。

它可以读取：

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

真正业务工具调用仍必须经过 ToolGateway。

## 4. RepositoryService 边界

RepositoryService 只暴露专用只读方法，不暴露完整订单对象。

建议方法：

```text
get_order_auth_context(order_id)
get_user_context(user_id)
get_open_ticket_by_idempotency_key(idempotency_key)
```

`get_order_auth_context(order_id)` 只返回权限预检需要的字段：

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

## 5. 二次确认流程

`CONFIRM_REQUIRED` 必须有恢复执行机制。

P0 使用 SQLite 存储 `pending_actions`，不使用纯内存。

pending_actions 至少包含：

```text
pending_action_id
session_id
source_run_id
user_id
action_plan_json
risk_level
status
expires_at
created_at
updated_at
```

status 枚举：

```text
PENDING
CONFIRMED
EXECUTED
EXPIRED
CANCELLED
```

默认过期时间：

```text
10 分钟
```

流程：

```text
PolicyService -> CONFIRM_REQUIRED
保存 ActionPlan 到 pending_actions
返回 pending_action_id
用户调用 /api/confirm
校验用户、状态、过期时间
复核 Policy
调用 ToolGateway
记录 Trace
```

## 6. /api/confirm 与 run_id

最终决定：

```text
POST /api/confirm 创建新的 run_id。
```

确认请求不是继续写入原 run，而是创建一个新的 Agent 执行链路。

字段关系：

```text
run_id：本次确认请求的新执行链路 ID
parent_run_id：原始触发 CONFIRM_REQUIRED 的 run_id
pending_action_id：待确认动作 ID
```

示例：

```text
run_001：用户请求修改地址，PolicyService 返回 CONFIRM_REQUIRED，生成 pa_001
run_002：用户确认 pa_001，parent_run_id = run_001，继续执行 ToolGateway
```

原因：

```text
一次 /api/chat 或 /api/confirm 对应一次 Agent 执行链路。
确认动作是新的用户输入，因此应创建新的 run_id。
parent_run_id 用于关联上下文。
```

## 7. ActionPlanValidator 与 PolicyService 边界

ActionPlanValidator 只负责结构合法性。

它负责：

```text
校验 LLM / Planner 输出是否为合法 JSON
校验 action 是否在允许动作集合中
校验 target_type 是否合法
校验 tool_name 是否在候选工具集合中
校验必要参数是否存在
校验是否存在明显危险动作
校验失败时返回 PLAN_INVALID 或 UNKNOWN_ACTION
```

它不负责：

```text
判断订单是否属于当前用户
判断租户是否一致
判断是否允许查询该订单
判断是否需要转人工
判断是否允许修改业务状态
```

PolicyService 负责真实权限与风险判断：

```text
读取只读 RepositoryService
判断用户是否拥有该资源
判断 tenant_id 是否一致
判断业务状态是否允许
判断 risk_level
返回 ALLOW / DENY / CONFIRM_REQUIRED / HUMAN_REQUIRED
```

一句话：

```text
Validator 管 ActionPlan 是否“像一个合法计划”。
PolicyService 管这个计划“当前用户能不能做、风险多高”。
```

LLM 输出不合法时：

```text
第一次尝试修复
修复失败则降级到 RuleBasedActionPlanner
仍失败则追问用户或转人工
```

## 8. RAG 边界

P0 不做真正 RAG。

P0 实现：

```text
knowledge_tool + 静态知识库 + sources
```

P1 再做：

```text
LangChain + 向量库 + 真正 RAG
```

不要让 RAG 拖慢 P0。

## 9. LangGraph 口径

P0 默认真实使用 LangGraph 编排。

但不做复杂：

```text
checkpoint
长期记忆
复杂 interrupt 恢复
复杂 UI
复杂子图
```

如果环境问题导致 LangGraph 无法完成，才允许临时实现 LangGraph-compatible workflow，并在 README 中说明。

## 10. run_id / trace 命名

统一命名：

```text
request_id：一次 HTTP 请求
session_id：一次用户会话
run_id：一次 Agent 执行链路
parent_run_id：跨请求恢复或确认时关联的上游 run
trace_node_id：单个节点 Trace 记录
```

`POST /api/chat` 返回 `run_id`。

P0 必须实现：

```text
GET /api/traces/{run_id}
```

P1 建议新增：

```text
GET /api/sessions/{session_id}/runs
```

## 11. 工单幂等规则

工单幂等键使用：

```text
idempotency_key = user_id + action + target_type + target_id
```

只拦截未关闭工单：

```text
OPEN
PROCESSING
```

如果存在未关闭工单，则返回已有工单，不重复创建。

如果工单已经：

```text
CLOSED
```

允许再次创建新工单。

## 12. 失败重试边界

ToolGateway 每次只执行一次工具调用。

FailureHandler 负责：

```text
判断是否 retryable
决定是否重试
决定是否降级
决定是否创建工单
写 failure_log
```

如果 FailureHandler 重试，则再次调用 ToolGateway，并在 `tool_call_logs` 中记录新的 attempt。

`tool_call_logs` 增加字段：

```text
run_id
tool_name
attempt_no
status
failure_type
latency_ms
created_at
```

示例：

```text
run_003, order_tool.query_order, attempt_no=1, FAILED, TOOL_TIMEOUT
run_003, order_tool.query_order, attempt_no=2, FAILED, TOOL_TIMEOUT
```

工具重试仍然属于同一个 `run_id`，不创建新的 `run_id`。

## 13. parent_run_id 使用规则

`parent_run_id` 主要用于跨请求链路关联。

适用场景：

```text
/api/confirm 确认 pending action
后续人工处理回调
后续恢复执行
```

不适用场景：

```text
ToolGateway 重试
FailureHandler 内部降级
同一次 Agent 执行链路内的 create_ticket
```

工具重试和失败降级仍在同一个 `run_id` 内记录。

工单可以记录：

```text
source_run_id
parent_run_id 可选
pending_action_id 可选
```

## 14. LLM 双模式

项目不能完全不接真实 LLM，但也不能依赖真实 LLM。

统一口径：

```text
P0：Rule Mode，稳定闭环
P0.5：LLM Mode，可选增强
P1：真正 RAG、外部平台、更完整 UI
```

Rule Mode：

```text
RuleBasedIntentClassifier
RuleBasedActionPlanner
默认启用
用于稳定测试、验收、失败场景、权限越界验证
```

LLM Mode：

```text
LLMIntentClassifier
LLMActionPlanner
LLMResponseGenerator
可选启用
用于最终展示真实大模型能力
```

配置方式：

```env
AGENT_PLANNER_MODE=rule
# or
AGENT_PLANNER_MODE=llm
```

如果 LLM 配置缺失、调用失败、返回格式错误，系统必须自动降级到 Rule Mode。

## 15. LLM 边界

真实 LLM 可以参与：

```text
意图识别
实体提取
ActionPlan 生成
复杂用户表达拆解
最终回复润色
```

真实 LLM 不可以参与最终裁决：

```text
不能决定是否允许访问数据
不能决定是否执行退款
不能决定是否修改地址
不能绕过 PolicyService
不能绕过 ToolGateway
不能直接调用业务工具
不能修改风险等级最终结果
不能覆盖 PolicyService 的 DENY / HUMAN_REQUIRED 结论
```

核心原则：

```text
LLM 只能生成候选 ActionPlan。
ActionPlan 必须经过 ActionPlanValidator。
ActionPlan 必须经过 PolicyService。
工具调用必须经过 ToolGateway。
```

## 16. LLMResponseGenerator 数据边界

允许传入：

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

禁止传入：

```text
完整手机号
完整地址
支付信息
完整订单对象
内部异常栈
系统 Prompt
API key
token
未脱敏工具结果
完整策略细节
```

LLMResponseGenerator 只能润色表达，不能改变业务结论。

例如：

```text
PolicyService = DENY
LLMResponseGenerator 不能改成 ALLOW。
```

## 17. 最新 P0 / P0.5 / P1 边界

### P0 必须完成

```text
FastAPI
真实 LangGraph 主流程
RuleBasedIntentClassifier
RuleBasedActionPlanner
ActionPlanValidator
PolicyService
RepositoryService 只读权限预检
ToolGateway
FailureHandler
TraceService
LoggingService
TicketService
PendingActionService
KnowledgeTool 静态知识库
20 条以上测试
8 个 Demo
```

### P0.5 建议完成

```text
LLMIntentClassifier
LLMActionPlanner
LLMResponseGenerator
LLM 调用失败自动降级 Rule Mode
LLM 输出 JSON schema 校验
README 中说明如何配置 LLM
```

### P1 后续完成

```text
真正 RAG：LangChain + 向量库
Telegram / Slack / 飞书接入
更完整前端
审计查询后台
更完整权限策略配置
```

## 18. LLM Mode 测试策略

Rule Mode 是主测试路径。

要求：

```text
Rule Mode 下 20 条核心测试必须稳定通过。
```

LLM Mode 只做少量可选测试，避免测试不稳定。

LLM Mode 测试重点不是回答内容，而是边界控制：

```text
LLM 输出非法 JSON -> Validator 拦截或降级
LLM 生成未知工具 -> DENY
LLM 生成退款直接执行 -> HUMAN_REQUIRED
LLM 试图越权 -> PolicyService 拦截
LLM 调用失败 -> fallback 到 Rule Mode
```

## 19. 技术债与后续强制要求

### 19.1 P0.5 ActionPlanValidator 技术债

P0 当前只拦截 forbidden action 可以接受。

P0.5 接入 LLM Mode 时，ActionPlanValidator 必须增加对以下字段的危险词扫描：

```text
tool_args
reason
```

原因：LLM 可能在合法 action 下，把越权意图、系统提示词请求、导出用户数据等危险内容藏在参数或 reason 中。

### 19.2 Phase 3 policy_logs 要求

后续完整链路接入前，PolicyService.evaluate 每次裁决都必须写入 `policy_logs`。

当前 Phase 2C 只完成规则裁决，可以暂不写库；Phase 3 接入链路时必须补齐。

### 19.3 PolicyService 规则拆分技术债

当前 P0 阶段，PolicyService 作为策略裁决入口可以保留。

后续当规则超过 8~10 个，或引入客服/主管/管理员角色权限时，需要重构为：

```text
PolicyService：只负责调度
PolicyRuleRegistry：负责 action -> rule 映射
BasePolicyRule：公共规则基类
QueryOrderRule / ChangeAddressRule / RefundRequestRule 等独立规则类
```

`_load_order_auth_context` 未来可以抽到 `BasePolicyRule`，作为订单类规则的公共归属校验。

注意：

```text
PolicyRule 仍然是确定性代码规则。
PolicyRule 不是 MCP Tool。
PolicyRule 不是 LLM Agent。
```

## 20. Codex 实现优先级

新的开发顺序：

1. 项目骨架
2. 核心数据结构：State / ActionPlan / PolicyDecision / ID 体系
3. RepositoryService，只读权限预检数据
4. LoggingService / TraceService
5. RuleBasedIntentClassifier / RuleBasedActionPlanner / ActionPlanValidator
6. PolicyService
7. ToolGateway
8. FailureHandler
9. TicketService + 幂等
10. PendingActionService + /api/confirm
11. LangGraph Workflow
12. API
13. 测试
14. Demo

## 21. 与旧文档冲突时的优先级

如果旧文档与本文件冲突，以本文件为准。

特别是：

- P0 不做真正 RAG，只需要 KnowledgeTool + 静态知识库 + sources。
- P0 强制真实 LangGraph，除非环境受阻。
- 使用 `run_id` 表示一次 Agent 执行链路。
- `/api/confirm` 创建新的 `run_id`，使用 `parent_run_id` 关联原始 run。
- PolicyService 可以读取只读 Mock Repository。
- ActionPlanValidator 不做真实权限判断。
- FailureHandler 负责重试，不是 ToolGateway。
- 工单幂等使用 `user_id + action + target_type + target_id`。
- Rule Mode 是 P0 主路径，LLM Mode 是 P0.5 可选增强。
