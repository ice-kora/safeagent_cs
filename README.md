# SafeAgent-CS

面向复杂客服场景的企业级受控 Agent 最小闭环系统。

当前实现阶段：P0-Phase 1。

## 本阶段已实现

- FastAPI 应用骨架
- `GET /api/health`
- 核心 ID 生成
- 核心数据结构
- SQLite 基础表初始化
- RepositoryService 只读权限预检
- LoggingService 结构化脱敏日志
- TraceService 按 `run_id` 写入 Trace

## 启动

```bash
uvicorn app.main:app --reload
```

访问：

```text
GET http://127.0.0.1:8000/api/health
```

## 测试

```bash
pytest
```

## 当前边界

本阶段不实现：

- `/api/chat`
- LangGraph Workflow
- PolicyService 详细规则
- ToolGateway 完整调用
- FailureHandler 重试降级
- PendingActionService 完整确认流程
- LLM Mode
- 真正 RAG
