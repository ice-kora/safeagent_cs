# SafeAgent-CS

## 项目名称

SafeAgent-CS：面向复杂客服场景的企业级受控 Agent 最小闭环系统

## 一句话定位

本项目不是完整客服平台，也不是普通 AI 客服聊天机器人，而是一个面向复杂客服场景的 **受控 Agent 控制内核**。它通过 ActionPlan、PolicyService、ToolGateway、FailureHandler、TraceLog 等模块，证明 Agent 在企业客服场景中如何安全、可控、可追踪地处理复杂问题。

## 项目背景

传统客服系统通常依赖规则树、FAQ、关键词匹配和固定流程，适合处理高频、确定性、标准化问题，例如查询物流、查询订单、退货规则、发票申请等。

但在真实平台客服场景中，用户问题经常具有以下特征：

- 表达不规范
- 多意图混合
- 涉及多个业务系统
- 涉及权限边界
- 涉及退款、投诉、改地址等高风险动作
- 涉及传统规则未覆盖的长尾问题
- 工具接口可能失败或超时
- 用户可能进行 Prompt Injection 或越权诱导

本项目的目标不是替代传统客服，而是在传统规则客服之上增加一个受控 Agent 层，用于复杂问题理解、任务拆解、工具编排、风险判断、人工接管和全链路追踪。

## 核心原则

1. P0 默认启用 Rule Mode，保证核心闭环稳定可测。
2. LLM Mode 仅作为 P0.5 可选增强，失败时必须自动降级到 Rule Mode。
3. LLM 只能生成候选 ActionPlan，不能直接调用业务接口。
4. ActionPlan 必须经过 ActionPlanValidator。
5. 所有业务动作必须经过 PolicyService 权限与风险校验。
6. 所有工具调用必须经过 ToolGateway。
7. 未知动作默认拒绝。
8. 高风险动作默认转人工。
9. 所有关键节点必须写入 TraceLog 和对应结构化日志。
10. 必须覆盖成功路径、失败路径、越权路径、高风险路径和降级路径。

## 核心闭环

```text
用户消息
  ↓
MessageNormalizer
  ↓
InputGuard
  ↓
IntentClassifier
  ↓
ActionPlanner
  ↓
ActionPlanValidator
  ↓
PolicyService
  ↓
RepositoryService 只读权限预检
  ↓
ToolGateway
  ↓
Mock Business Tools
  ↓
FailureHandler / TicketService / ResponseGenerator
  ↓
TraceLog / AuditLog
```

## 推荐技术栈

| 技术 | 用途 |
|---|---|
| FastAPI | 后端接口服务 |
| LangGraph | Agent 工作流编排 |
| LangChain | P1 真正 RAG，可选 |
| SQLite | 本地轻量持久化，包含 pending_actions 和日志表 |
| JSON Mock | 模拟订单、用户、工单、物流、失败场景 |
| pytest | 测试 |
| Streamlit / Gradio | 可选演示界面 |
| Telegram / Slack / 飞书 | 可选消息平台接入 |

## P0 范围

P0 必须完成：

- `/api/chat` 聊天接口
- `/api/confirm` 二次确认接口
- `GET /api/traces/{run_id}` Trace 查询接口
- 真实 LangGraph 主流程
- State 定义
- RuleBasedIntentClassifier
- RuleBasedActionPlanner
- ActionPlanValidator
- RepositoryService 只读权限预检
- PolicyService
- ToolGateway
- Mock Tools
- TicketService
- PendingActionService
- TraceLog
- LoggingService
- FailureHandler
- KnowledgeTool 静态知识库和 sources
- 至少 20 条测试用例
- 至少 8 个 Demo 场景

## P0.5 范围

P0.5 建议完成：

- LLMIntentClassifier
- LLMActionPlanner
- LLMResponseGenerator
- LLM 调用失败自动降级 Rule Mode
- LLM 输出 JSON schema 校验
- README 中说明 `AGENT_PLANNER_MODE=rule|llm`

## P1 范围

P1 建议完成：

- 真正 RAG：LangChain + 向量库
- 人工接管回调模拟
- `GET /api/sessions/{session_id}/runs`
- 一个真实消息平台接入，例如 Telegram、Slack 或飞书
- 更完整前端和审计查询后台

## P2 暂不实现

本项目三天内不实现：

- 真实支付
- 真实退款
- 完整用户注册登录
- 复杂权限后台
- 复杂客服排班
- 多租户管理后台
- 生产级监控大盘
- 复杂前端系统

## 核心 Demo 场景

1. 查询退货政策：KnowledgeTool 静态知识库回答并展示来源。
2. 查询本人订单：PolicyService 允许，ToolGateway 调用订单工具。
3. 查询他人订单：PolicyService 拒绝，记录越权日志。
4. 修改地址：中风险动作，生成 pending_action_id，用户通过 `/api/confirm` 确认。
5. 申请退款：高风险动作，创建工单并转人工。
6. 投诉客服：高风险投诉工单，转人工。
7. Prompt Injection：InputGuard 或 PolicyService 拒绝。
8. 订单工具超时：FailureHandler 重试、降级、创建工单。

## 项目价值

本项目证明的不是“AI 可以回答客服问题”，而是：

- Agent 如何与传统业务系统安全集成。
- Agent 如何避免越权操作。
- Agent 如何处理工具失败。
- Agent 如何将复杂客服问题结构化。
- Agent 如何通过 TraceLog 实现可观测与可审计。
- Agent 如何通过 PolicyService 与 ToolGateway 实现企业级边界控制。

## 运行目标

最终应支持：

```bash
uvicorn app.main:app --reload
```

然后通过：

```bash
POST /api/chat
POST /api/confirm
GET /api/traces/{run_id}
GET /api/tickets
```

完成核心演示。


## 日志与审计

当前阶段必须实现基础日志能力。每次 `/api/chat` 和 `/api/confirm` 都必须生成新的 `run_id`：

- application.log：系统运行日志
- agent_traces：Agent 节点执行轨迹
- policy_logs：权限与风险决策日志
- tool_call_logs：工具调用日志
- failure_logs：失败处理日志
- security_logs：越权、注入、敏感请求等安全日志

完整设计见：

```text
docs/11_LOGGING_AUDIT_DESIGN.md
```

注意：当前阶段不实现完整审计平台，但日志结构必须为后续 AuditService 预留。


## Codex Review 修正

Codex 审阅后提出的实现风险点已整理为修正文档：

```text
docs/12_CODEX_REVIEW_FIXES.md
```

如果早期文档与该修正文档冲突，以 `12_CODEX_REVIEW_FIXES.md` 为准。

关键修正包括：

- PolicyService 可以读取只读 Mock Repository 做权限预检。
- P0 使用 knowledge_tool + 静态知识库，真正 RAG 放入 P1。
- 引入 run_id 表示一次 Agent 执行链路。
- 用户二次确认通过 pending_action_id 和 `/api/confirm` 完成，确认请求创建新的 run_id，并用 parent_run_id 关联原始 run。
- FailureHandler 负责重试，ToolGateway 只执行一次工具调用。
- 工单幂等使用 user_id + action + target_type + target_id。
