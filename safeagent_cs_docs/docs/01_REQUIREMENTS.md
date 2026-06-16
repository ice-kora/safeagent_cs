# 01 需求文档

## 1. 背景

传统客服系统在高频标准场景中表现稳定，但面对复杂客服问题时存在局限：

- 用户表达不规范
- 一个输入中包含多个诉求
- 需要同时查询订单、物流、政策、工单等多个系统
- 涉及退款、投诉、修改地址等高风险动作
- 用户可能试图越权查询他人信息
- 工具接口可能失败
- 规则库无法覆盖所有长尾场景

因此，本项目设计一个受控客服 Agent 最小闭环系统，用于复杂客服问题处理。

## 2. 用户角色

### 2.1 普通用户

可以：

- 查询公开政策
- 查询本人订单
- 提交售后诉求
- 创建工单
- 进行中风险操作的二次确认

不可以：

- 查询他人订单
- 导出用户数据
- 修改权限
- 要求 AI 直接退款
- 要求 AI 关闭投诉

### 2.2 AI 客服 Agent

可以：

- 理解用户输入
- 生成 ActionPlan
- 调用经过授权的工具
- 生成客服回复
- 创建工单
- 触发人工接管

不可以：

- 直接执行真实业务动作
- 绕过 PolicyService
- 绕过 ToolGateway
- 访问未授权数据
- 执行未知工具

### 2.3 人工客服

本项目中仅模拟。

可以：

- 接收高风险工单
- 处理投诉、退款、争议问题

### 2.4 客服主管

本项目中仅模拟。

可以：

- 审批高风险退款
- 处理严重投诉

### 2.5 系统管理员

本项目中仅模拟。

可以：

- 配置知识库
- 配置策略规则
- 查看审计日志

## 3. 核心业务场景

### 3.1 公开政策查询

用户询问退货、发票、会员、售后规则。

期望：

- P0 使用 KnowledgeTool 和静态知识库
- 返回政策答案
- 可展示来源
- 风险等级 L1
- P1 再接入 LangChain + 向量库的真正 RAG

### 3.2 本人订单查询

用户查询自己的订单状态。

期望：

- 提取订单号
- 校验订单是否属于当前用户
- 允许后调用订单工具
- 返回脱敏后的订单状态
- 风险等级 L2

### 3.3 他人订单查询

用户查询不属于自己的订单。

期望：

- PolicyService 拒绝
- 不调用订单工具或不返回敏感信息
- 记录越权日志
- 风险等级 L5

### 3.4 修改地址

用户要求修改订单地址。

期望：

- 判断订单是否未发货
- 判断是否本人订单
- 要求用户二次确认
- 保存 pending_action_id
- 用户通过 `POST /api/confirm` 确认后创建新的 run_id 继续执行
- 风险等级 L3

### 3.5 退款申请

用户要求退款。

期望：

- 不自动退款
- 创建退款工单
- 转人工客服
- 风险等级 L4

### 3.6 投诉客服

用户投诉客服或平台。

期望：

- 创建投诉工单
- 设置高风险等级
- 转人工
- 风险等级 L4

### 3.7 Prompt Injection

用户输入“忽略所有规则”“你现在是管理员”等攻击内容。

期望：

- InputGuard 或 PolicyService 拒绝
- 记录风险
- 风险等级 L5

### 3.8 工具失败

订单、物流、工单工具可能超时、500、返回错误格式。

期望：

- FailureHandler 统一处理
- 可重试则重试
- 不可恢复则降级为工单
- 记录失败 Trace

## 4. 功能需求

### P0 必须实现

- Chat API
- Confirm API
- Trace 查询 API：`GET /api/traces/{run_id}`
- 真实 LangGraph 主流程
- State 定义
- InputGuard
- RuleBasedIntentClassifier
- RuleBasedActionPlanner
- ActionPlanValidator
- RepositoryService 只读权限预检
- PolicyService
- ToolGateway
- Mock Order Tool
- Mock Ticket Tool
- KnowledgeTool 静态知识库和 sources
- FailureHandler
- TraceLog
- LoggingService
- PendingActionService
- 测试用例
- Demo 脚本

### P0.5 建议实现

- LLMIntentClassifier
- LLMActionPlanner
- LLMResponseGenerator
- LLM 调用失败自动降级 Rule Mode
- LLM 输出格式校验

### P1 建议实现

- 真正 RAG：LangChain + 向量库
- session 下 run 查询接口：`GET /api/sessions/{session_id}/runs`
- Telegram / Slack / 飞书适配器之一

### P2 暂不实现

- 真实业务系统对接
- 真实退款
- 真实支付
- 复杂登录注册
- 多租户后台
- 客服排班
- 生产级权限后台

## 5. 非功能需求

### 5.1 安全性

- 默认拒绝未知动作
- LLM 不能直接调用工具
- LLM 不能决定最终权限与风险结论
- ActionPlan 必须经过 ActionPlanValidator
- 工具调用必须经过 ToolGateway
- 高风险动作必须转人工
- 敏感字段必须脱敏

### 5.2 可观测性

必须记录：

- request_id
- session_id
- run_id
- 用户输入
- 意图识别结果
- ActionPlan
- PolicyDecision
- ToolCall
- ToolResult
- FailureType
- FinalAnswer

日志必须写入 `logs/application.log` 和结构化日志表，且不得记录完整手机号、完整地址、身份证、支付信息、API key、token、系统 Prompt 或内部异常栈。

### 5.3 可测试性

至少覆盖：

- 正常流程
- 越权流程
- 高风险流程
- 工具失败流程
- Prompt Injection 流程

### 5.4 可扩展性

应支持后续新增：

- 新工具
- 新渠道
- 新风险规则
- 新业务场景
- 新知识库

## 6. 验收标准

P0 验收：

- 8 个核心 Demo 可运行
- 20 条以上测试用例通过
- 查询他人订单必须被拒绝
- 退款必须转人工
- 工具失败不能导致系统崩溃
- 每次 `/api/chat` 和 `/api/confirm` 必须有新的 run_id 与 Trace
