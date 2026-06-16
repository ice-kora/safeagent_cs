# 00 项目总览文档

## 1. 项目定位

SafeAgent-CS 是一个面向复杂客服场景的企业级受控 Agent 最小闭环系统。

它不是完整客服平台，而是一个 Agent 控制内核，重点解决：

- 复杂问题理解
- 多意图拆解
- 权限越界控制
- 工具调用治理
- 失败场景降级
- 高风险动作转人工
- 全链路 Trace 可观测

## 2. 项目不是做什么

本项目不是：

- 普通 FAQ 机器人
- 纯聊天机器人
- 完整 SaaS 客服系统
- 真实交易系统
- 真实退款系统
- 完整 CRM 系统

## 3. 项目要证明什么

本项目要证明：

```text
传统客服负责高频确定性问题。
Agent 层负责复杂、长尾、多意图、跨系统、高风险问题。
PolicyService 和 ToolGateway 保证 Agent 不能越权。
TraceLog 保证每一步可追踪、可解释、可复盘。
```

## 3.1 最新范围口径

当前文档包以 `docs/11_LOGGING_AUDIT_DESIGN.md` 和 `docs/12_CODEX_REVIEW_FIXES.md` 为最高优先级。

P0 采用：

- Rule Mode：规则型 IntentClassifier 和 ActionPlanner，默认启用。
- 真实 LangGraph 主流程：不做复杂 checkpoint、长期记忆、复杂 interrupt 或复杂子图。
- KnowledgeTool：静态知识库和 sources，不做真正 RAG。
- SQLite：存储 Trace、日志、工单和 pending_actions。

P0.5 可选增强：

- LLMIntentClassifier
- LLMActionPlanner
- LLMResponseGenerator
- LLM 失败自动降级 Rule Mode

P1 再做：

- LangChain + 向量库的真正 RAG
- 外部消息平台接入
- 更完整前端
- 审计查询后台

## 4. 面试表达

如果面试官问：

> 现在传统客服已经很成熟，这个项目有什么意义？

回答：

> 如果只是做 FAQ 或查询订单，这个项目确实意义有限。我的项目定位不是替代传统客服，而是在传统规则客服之上增加一个受控 Agent 层。它主要处理传统客服覆盖成本较高的复杂场景，比如多意图混合、跨系统查询、长尾售后争议、退款投诉等高风险动作。系统中 LLM 不直接操作业务接口，只生成 ActionPlan，真正的执行由 PolicyService 和 ToolGateway 控制，高风险动作转人工，全链路记录 Trace。因此它的核心价值是复杂客服场景下的受控流程编排，而不是多一个聊天机器人。

## 5. 最小闭环

```text
用户输入
  ↓
输入安全检查
  ↓
意图识别
  ↓
ActionPlan 生成
  ↓
ActionPlanValidator
  ↓
权限与风险校验
  ↓
工具网关调用
  ↓
失败处理 / 工单创建 / 回复生成
  ↓
Trace 记录
```

## 6. 三天交付目标

三天内交付：

- 可运行后端项目
- 核心 Agent 工作流
- Mock 业务工具
- 权限控制
- 失败场景模拟
- 工单流转
- Trace 记录
- 测试用例
- Demo 脚本
- 项目文档

## 7. 评判标准

不以页面数量评判。

以以下标准评判：

- 成功路径是否跑通
- 权限越界是否拦截
- 高风险动作是否转人工
- 工具失败是否兜底
- Trace 是否完整
- 测试是否覆盖核心风险

## 8. 统一 ID 口径

```text
request_id：一次 HTTP 请求
session_id：一次用户会话
run_id：一次 Agent 执行链路
trace_node_id：单个节点 Trace 记录
```

`POST /api/chat` 和 `POST /api/confirm` 都会创建新的 `run_id`。确认流程使用 `parent_run_id` 关联原始触发 `CONFIRM_REQUIRED` 的执行链路。
