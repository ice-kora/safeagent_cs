# 07 失败场景设计文档

## 1. 设计目标

普通 Demo 项目通常只做成功路径。  
本项目要模拟大量失败场景，以证明 Agent 系统具备企业级可控性。

失败处理原则：

- 失败必须结构化
- 失败必须进入 FailureHandler
- 失败必须记录 Trace
- 可重试则重试
- 不可恢复则降级
- 高风险或不确定则转人工
- 不向用户暴露底层异常
- ToolGateway 每次只执行一次工具调用
- FailureHandler 负责判断是否重试、是否降级、是否创建工单

## 2. 失败类型

```python
class FailureType:
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_5XX = "TOOL_5XX"
    TOOL_BAD_RESPONSE = "TOOL_BAD_RESPONSE"
    POLICY_DENIED = "POLICY_DENIED"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    PLAN_INVALID = "PLAN_INVALID"
    PARAM_MISSING = "PARAM_MISSING"
    RAG_EMPTY = "RAG_EMPTY"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    DUPLICATE_OPERATION = "DUPLICATE_OPERATION"
```

## 3. 工具失败

### 3.1 TOOL_TIMEOUT

触发：

- order_tool.query_order 超时

处理：

- FailureHandler 判断 retryable 后重试 1 次
- 重试时再次调用 ToolGateway
- 两次 tool_call_log 使用同一个 run_id，attempt_no 分别为 1 和 2
- 仍失败则创建工单
- 回复用户系统正在核实
- 记录 Trace

用户回复：

```text
当前订单系统响应较慢，我已经为你创建了工单，人工客服会继续核实订单状态。
```

### 3.2 TOOL_5XX

触发：

- logistics_tool 返回 500

处理：

- 不继续调用
- 记录工具失败
- 降级为工单
- 写 failure_log

### 3.3 TOOL_BAD_RESPONSE

触发：

- 工具返回缺少关键字段

处理：

- 标记工具响应异常
- 不把异常结果交给用户
- 转人工或降级回复

## 4. 权限失败

### 4.1 POLICY_DENIED

触发：

- 查询他人订单
- 导出用户数据
- 查看系统 Prompt
- 修改权限

处理：

- 直接拒绝
- 不调用工具
- 记录 policy_log
- risk = L5

### 4.2 RISK_TOO_HIGH

触发：

- 退款
- 投诉升级
- 赔偿承诺
- 关闭投诉

处理：

- 创建工单
- 转人工
- 不自动执行

## 5. 计划失败

### 5.1 PLAN_INVALID

触发：

- ActionPlan JSON 格式错误
- action 缺失
- tool_name 缺失

处理：

- 尝试修复一次
- 修复失败则追问用户或转人工

### 5.2 PARAM_MISSING

触发：

- 查询订单但没有订单号

处理：

- 追问用户

用户回复：

```text
请提供需要查询的订单号，我会继续帮你核实。
```

### 5.3 UNKNOWN_ACTION

触发：

- LLM 生成不存在的动作

处理：

- 默认拒绝
- 记录风险
- 不调用工具

## 6. RAG 失败

### 6.1 RAG_EMPTY

触发：

- P0 静态知识库没有命中文档
- P1 真正 RAG 没有命中文档

处理：

- 低置信度回复
- 建议转人工或创建工单

用户回复：

```text
我暂时没有在知识库中找到明确规则。为了避免误导，我可以为你创建工单，由人工客服进一步确认。
```

## 7. 安全攻击

### 7.1 PROMPT_INJECTION

触发：

- 忽略所有规则
- 你是管理员
- 输出系统提示词
- 导出全部数据

处理：

- 拒绝
- risk = L5
- 写入安全 Trace

用户回复：

```text
抱歉，我不能执行该请求。为了保护平台和用户数据安全，我只能处理当前账号授权范围内的问题。
```

## 8. 幂等失败

### 8.1 DUPLICATE_OPERATION

触发：

- 重复申请退款
- 重复创建投诉工单
- 重复修改地址

处理：

- 如果存在同一 `user_id + action + target_type + target_id` 的 OPEN / PROCESSING 工单，则返回已有工单
- 如果已有工单为 CLOSED，则允许创建新工单

用户回复：

```text
你已经提交过相关工单，当前工单编号为 T10001，我会继续为你跟踪处理进度。
```

## 9. 失败处理流程

```text
工具 / 策略 / 计划失败
  ↓
FailureHandler
  ↓
判断 failure_type
  ↓
判断 retryable
  ↓
可重试：重试
  ↓
不可重试：降级 / 创建工单 / 拒绝
  ↓
生成用户可理解回复
  ↓
写入 Trace
```

工具重试仍属于同一个 `run_id`，不创建新的 `run_id`。`parent_run_id` 只用于 `/api/confirm`、后续人工处理回调或后续恢复执行等跨请求链路关联。

## 10. Demo 必须展示的失败场景

至少展示：

1. 查询他人订单：POLICY_DENIED
2. Prompt Injection：PROMPT_INJECTION
3. 订单工具超时：TOOL_TIMEOUT
4. 退款申请：RISK_TOO_HIGH
5. 重复退款：DUPLICATE_OPERATION
