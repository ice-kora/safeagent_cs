# SafeAgent-CS

SafeAgent-CS 是面向复杂客服场景的企业级受控 Agent 最小闭环系统。

当前阶段：P0 Rule Mode 主流程闭环。项目重点不是“让大模型直接调用工具”，而是展示一个可审计、可测试、可二次确认的受控 Agent 架构。

## 项目定位

SafeAgent-CS 的 P0 目标是实现企业客服场景里的最小安全闭环：

- 用户请求进入统一入口。
- 系统先做意图识别和候选计划生成。
- 候选计划必须经过结构校验、权限与风险裁决。
- 工具调用必须经过受控网关。
- 中风险动作必须先进入二次确认。
- 全链路写入 `run_id`、Trace 和结构化日志。

## 核心入口

当前有两个核心 API：

- `/api/chat`：首次用户请求入口。
- `/api/confirm`：二次确认恢复入口。

`/api/chat` 每次请求都会创建新的 `request_id` 和 `run_id`，用于记录本次 Agent 执行链路。

`/api/confirm` 不复用原始 `run_id`，而是创建新的 `run_id`，并通过 `parent_run_id` 关联原始触发 `CONFIRM_REQUIRED` 的请求。

## 主流程

P0 主流程如下：

```text
用户请求
  -> IntentClassifier
  -> ActionPlanner
  -> ActionPlanValidator
  -> PolicyService
  -> ToolGateway / PendingAction / HumanRequired / Deny
```

对应分支：

- `ALLOW`：通过 `ToolGateway` 调用工具。
- `DENY`：拒绝执行，不调用工具。
- `CONFIRM_REQUIRED`：创建 `pending_action`，等待 `/api/confirm`。
- `HUMAN_REQUIRED`：返回人工处理结果，P0 暂不自动创建复杂工单流转。

## 安全边界

当前 P0 严格保留四个安全边界：

1. Validator 失败不进入 PolicyService。
2. PolicyService 不放行不进入 ToolGateway。
3. 工具调用只能经过 ToolGateway。
4. `CONFIRM_REQUIRED` 只创建 `pending_action`，不直接执行工具。

补充边界：

- `/api/chat` 不直接调用任何 Mock Tool。
- `/api/confirm` 执行前必须重新经过 PolicyService 复核。
- 未知 `PolicyDecision` 默认安全失败，不进入工具执行。
- ToolGateway 不做权限判断，也不负责重试。
- FailureHandler 重试时仍必须再次调用 ToolGateway。

## 当前能力

- FastAPI 应用骨架。
- `GET /api/health` 健康检查。
- `POST /api/chat` 首次用户请求主入口。
- `POST /api/confirm` 二次确认恢复入口。
- RuleBasedIntentClassifier 规则意图识别。
- RuleBasedActionPlanner 规则 ActionPlan 生成。
- ActionPlanValidator 结构校验。
- PolicyService 权限与风险裁决。
- RepositoryService 只读权限预检。
- ToolGateway 工具白名单、路由、脱敏日志。
- FailureHandler 工具失败收口与一次重试。
- PendingActionService 二次确认存储与状态流转。
- TraceService 记录 `agent_runs` 和 `agent_traces`。
- Mock Tools：知识库查询、订单查询、地址修改模拟、工单创建。

## Demo

运行 8 个标准演示场景：

```bash
python demo_safeagent_cs.py
```

Demo 覆盖：

1. 查询公开政策：`/api/chat -> SUCCESS`
2. 查询本人订单 `O10086`：`/api/chat -> SUCCESS`
3. 查询他人订单 `O10087`：`/api/chat -> DENY`
4. 修改未发货订单地址 `O10086`：`/api/chat -> CONFIRM_REQUIRED`
5. 使用 `/api/confirm` 确认 pending_action：`-> EXECUTED`
6. 退款请求：`/api/chat -> HUMAN_REQUIRED`
7. 投诉请求：`/api/chat -> HUMAN_REQUIRED`
8. Prompt Injection：`/api/chat -> DENY`

## 启动服务

```bash
uvicorn app.main:app --reload
```

健康检查：

```text
GET http://127.0.0.1:8000/api/health
```

## 运行测试

```bash
python -m pytest
```

当前基线：

```text
132 passed, 1 warning
```

warning 为第三方 `TestClient` 弃用提示，不影响当前 P0 验收。

## 当前未实现

当前阶段未实现以下内容：

- LangGraph Workflow
- LLM Mode
- 真实 RAG
- 前端
- 外部平台接入
- 完整客服后台多角色权限模型
- 复杂人工工单流转后台

这些内容属于后续 P0.5 / P1 范围，不属于当前 P0 主闭环。
