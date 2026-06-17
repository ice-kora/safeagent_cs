# SafeAgent-CS

SafeAgent-CS 是一个企业级受控客服 Agent 执行平台。项目重点不是让 LLM（大语言模型）直接接管业务，而是把意图识别、计划生成、RAG（检索增强生成）和工具调用放进可审计、可测试、可回滚的安全执行框架里。

当前阶段：v0.3 Engineering Closure。

当前核心结论：

```text
LLM / Planner / RAG only propose candidates.
PolicyService / ToolGateway / PendingActionService / FailureHandler decide whether execution is allowed, confirm-required, human-required, denied, or safely failed.
```

## 1. 项目定位

SafeAgent-CS 面向电商客服、售后、订单咨询等高风险业务场景，提供一个可落地的受控 Agent 最小平台：

- 首次请求进入 `/api/chat`。
- 二次确认进入 `/api/confirm`。
- Planner 只能生成候选 `ActionPlan`。
- Validator 负责结构合法性。
- PolicyService 负责权限与风险裁决。
- ToolGateway 是唯一工具入口。
- PendingActionService 负责二次确认状态。
- FailureHandler 负责工具失败收口。
- Trace / Logs 负责链路观察与问题追踪。

## 2. 核心安全原则

1. LLM 不直接调用工具。
2. RAG 不参与权限裁决。
3. ActionPlanValidator 失败不进入 PolicyService。
4. PolicyService 不放行不进入 ToolGateway。
5. 工具调用只能经过 ToolGateway。
6. `CONFIRM_REQUIRED` 只创建 pending action，不直接执行工具。
7. `/api/confirm` 必须重新经过 PolicyService 复核。
8. FailureHandler 重试仍必须通过 ToolGateway。
9. Trace 和日志必须脱敏。
10. Checkpoint / Resume 当前只做 readiness，不启用真实恢复执行。

## 3. 系统架构

```text
User
  -> /api/chat
  -> IntentClassifier
  -> ActionPlanner
  -> LLMOutputGuard
  -> ActionPlanValidator
  -> PolicyService
  -> route
      -> ALLOW -> ToolGateway -> FailureHandler
      -> CONFIRM_REQUIRED -> PendingActionService
      -> HUMAN_REQUIRED -> HumanRequired
      -> DENY -> Deny
  -> ResponseGeneration
  -> LLMResponseGuard
  -> Trace / Logging
```

核心分层：

- `app/api/`：HTTP API（应用程序编程接口）入口。
- `app/core/`：核心数据结构、常量、校验结果。
- `app/services/`：安全内核与业务服务。
- `app/tools/`：Mock 工具与受控工具能力。
- `app/rag/`：本地轻量 RAG 能力。
- `app/workflows/`：workflow 编排、LangGraph engine、checkpoint readiness。
- `app/evaluation/`：安全回归与 RAG 评测。
- `tests/`：确定性测试。

## 4. 主链路流程

`/api/chat` 是首次请求入口：

```text
request
  -> start run
  -> intent classification
  -> action planning
  -> action plan validation
  -> policy decision
  -> route
  -> trace / logs
  -> response
```

`/api/confirm` 是二次确认恢复入口：

```text
pending_action_id
  -> validate pending_action
  -> create new run_id
  -> parent_run_id = source_run_id
  -> PolicyService re-check
  -> ToolGateway
  -> mark executed / cancelled
```

## 5. Workflow 配置

当前支持两层配置。

### Workflow Mode

```env
SAFEAGENT_WORKFLOW_MODE=manual
```

支持值：

- `manual`：默认值，继续走手写主链路。
- `workflow`：走 workflow adapter。

非法值回退 `manual`，避免误开实验路径。

### Workflow Engine

```env
SAFEAGENT_WORKFLOW_ENGINE=style
```

支持值：

- `style`：LangGraph-style 轻量执行器。
- `langgraph`：真实 LangGraph chat workflow engine。

engine 只在 `SAFEAGENT_WORKFLOW_MODE=workflow` 时生效。非法值回退 `style`。

## 6. RAG KnowledgeTool

当前 RAG 是本地轻量 MVP（最小可行产品）：

- 只服务 `knowledge_tool.query_policy`。
- 使用静态政策语料。
- 支持 chunk、retrieval、rerank 和 citation quality eval。
- 返回 answer、sources 和安全摘要。
- 不参与订单权限裁决。
- 不替代 PolicyService。

## 7. Safety Regression

项目内置 manual / workflow 双轨安全回归评测：

- 对比 manual 与 workflow 的状态、工具调用、pending action、Trace。
- 支持 intentional difference 机制。
- `failed_cases` 会统计所有未通过 case，避免隐藏预期差异中的真实失败。
- 用于验证 workflow 接入不破坏安全语义。

## 8. LangGraph Chat Workflow

v0.3 已接入真实 LangGraph chat workflow engine，但默认不启用。

LangGraph 只负责编排：

- 节点顺序。
- 条件路由。
- 状态传递。
- 为后续 checkpoint / resume 准备。

LangGraph 不负责：

- 权限判断。
- 工具执行。
- pending action 状态管理。
- 失败重试策略。
- LLM 输出安全裁决。

这些仍由现有服务负责。

## 9. Checkpoint / Resume Readiness

当前只完成 readiness，不启用真实 resume：

- JSON-safe checkpoint snapshot。
- schema version。
- checkpoint / resume 协议判断。
- 内存版 checkpoint store。
- resume dry-run。
- tool resume readiness。
- pending action resume readiness。
- checkpoint resume matrix。

明确未做：

- 未启用 LangGraph checkpointer。
- 未接 `MemorySaver` / `SQLiteSaver`。
- 未新增 `/api/resume`。
- 未恢复执行工具。
- 未重复创建 pending action。

## 10. 快速启动

安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
uvicorn app.main:app --reload
```

健康检查：

```text
GET http://127.0.0.1:8000/api/health
```

## 11. Demo

P0 标准 API Demo：

```bash
python demo_safeagent_cs.py
```

v0.3 本地能力 Demo：

```bash
python demo_v03_safeagent.py
```

`demo_v03_safeagent.py` 不启动服务、不接外部网络、不接真实 LLM，使用临时 SQLite 展示：

1. policy query 成功。
2. 本人订单查询成功。
3. 他人订单查询 DENY。
4. 地址修改进入 CONFIRM_REQUIRED。
5. 退款进入 HUMAN_REQUIRED。
6. 真实 LangGraph engine 运行一次。
7. checkpoint snapshot 生成。
8. checkpoint store 保存。
9. resume dry-run 到 `policy_node` 允许。
10. resume dry-run 到 `tool_gateway_node` 被拒绝。

## 12. 测试命令

全量测试：

```bash
python -m pytest
```

重点回归：

```bash
python -m pytest tests/test_chat_api.py tests/test_chat_workflow_mode.py
python -m pytest tests/test_confirm_api.py tests/test_confirm_workflow_mode.py
python -m pytest tests/test_langgraph_chat_workflow.py
python -m pytest tests/test_workflow_safety_regression.py
python -m pytest tests/test_rag_knowledge_tool.py tests/test_rag_evaluation.py
python -m pytest tests/test_checkpoint_store.py tests/test_checkpoint_resume_protocol.py
python -m pytest tests/test_demo_v03.py
```

## 13. 当前测试基线

Phase 12A 完成前基线：

```text
317 passed, 1 warning
```

Phase 12A 新增 v0.3 demo 测试后，本地执行结果以当前 `python -m pytest` 输出为准。

warning 为第三方 `TestClient` 弃用提示，不影响当前验收。

## 14. 项目边界

当前未实现：

- 真实 LLM Provider Adapter。
- 真实外部向量数据库。
- 真实 LangGraph checkpoint 持久化。
- 真实 resume 执行。
- `/api/resume`。
- MCP 工具接入。
- 前端控制台。
- 完整 AuthN/AuthZ（认证与授权）体系。
- 多租户生产隔离。
- 真实订单、支付、退款系统接入。

## 15. Roadmap

建议后续按风险递增推进：

1. LLM Provider Adapter：先接理解层和计划层，仍经过 Guard / Validator / Policy / ToolGateway。
2. 真实向量检索：替换本地轻量 RAG，但不参与权限裁决。
3. Tool idempotency persistence：为真实 resume 和重复调用防护补齐事实源。
4. Pending action event sourcing：补齐状态流转审计。
5. Real checkpoint：在 checkpoint/readiness 测试充分后接 LangGraph checkpointer。
6. MCP adapter：把外部工具接入 ToolGateway，而不是绕过 ToolGateway。
7. Frontend console：展示 runs、traces、policy logs、tool logs、failure logs。
8. AuthN/AuthZ hardening：补齐企业级身份、角色、租户隔离。
