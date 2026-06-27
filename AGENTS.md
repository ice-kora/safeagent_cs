# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目定位

SafeAgent-CS 是企业级受控客服 Agent 执行平台，面向电商客服、售后、订单咨询等高风险业务场景。

**核心安全原则（必须遵守，不可绕过）：**

```
LLM / Planner / RAG only propose candidates.
PolicyService / ToolGateway / PendingActionService / FailureHandler decide whether execution is allowed.
```

1. LLM 不直接调用工具——只能生成候选 ActionPlan。
2. RAG 不参与权限裁决——只提供证据和知识检索。
3. 所有工具调用必须经过 `ToolGateway`（唯一工具入口）。
4. `ActionPlanValidator` 失败不进入 `PolicyService`。
5. `PolicyService` 不放行不进入 `ToolGateway`。
6. `CONFIRM_REQUIRED` 只创建 pending action，不直接执行工具。
7. `/api/confirm` 必须重新经过 `PolicyService` 复核。
8. `FailureHandler` 重试仍必须通过 `ToolGateway`。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload

# 全量测试
python -m pytest

# 运行单个测试文件
python -m pytest tests/test_chat_api.py

# 按关键字筛选运行
python -m pytest -k "intent"

# 核心安全回归（改动后必跑）
python -m pytest tests/test_chat_api.py tests/test_chat_workflow_mode.py
python -m pytest tests/test_confirm_api.py tests/test_confirm_workflow_mode.py
python -m pytest tests/test_langgraph_chat_workflow.py
python -m pytest tests/test_workflow_safety_regression.py
```

项目没有配置 lint/format/coverage 工具。

## 运行时配置（Profile 系统）

通过环境变量 `SAFEAGENT_PROFILE` 控制，合法值：`dev`（默认）、`demo`、`prod`。非法值回退 `dev`。

| Profile | workflow_mode | workflow_engine | llm_mode | db_backend | runtime_backend | tool_backend | RAG vector_store |
|---------|--------------|-----------------|----------|------------|-----------------|-------------|------------------|
| dev | manual | style | rule | sqlite | sqlite | mock | memory |
| demo | workflow | langgraph | rule | postgres | postgres | mock | milvus |
| prod | workflow | langgraph | real_llm | postgres | postgres | external_stub | milvus |

关键环境变量（详见 `.env.example`）：
- `SAFEAGENT_PROFILE` — 运行 Profile
- `SAFEAGENT_WORKFLOW_MODE` — `manual` / `workflow`
- `SAFEAGENT_WORKFLOW_ENGINE` — `style` / `langgraph`（仅 workflow 模式生效）
- `SAFEAGENT_LLM_MODE` — `rule` / `mock_llm` / `real_llm`
- `SAFEAGENT_DB_BACKEND` — `sqlite` / `postgres`
- `SAFEAGENT_TOOL_BACKEND` — `mock` / `external_stub`
- `DATABASE_URL` — PostgreSQL 连接串

环境配置文件加载顺序：`.env` → `.env.local`，已设置的进程环境变量不会被覆盖。

配置文件入口：`app/core/config.py` → `get_settings()`，由 `app/core/profiles.py` 提供各 profile 默认值。

## 架构概览

```
User
  → /api/chat
  → IntentClassifier → ActionPlanner → ActionPlanValidator
  → PolicyService → route:
      ALLOW           → ToolGateway → FailureHandler
      CONFIRM_REQUIRED → PendingActionService
      HUMAN_REQUIRED   → 人工处理
      DENY             → 拒绝
  → ResponseGeneration → Trace/Logging
```

### 分层职责

| 层 | 目录 | 负责 | 禁止 |
|----|------|------|------|
| API | `app/api/` | HTTP 传输、Pydantic 输入校验、依赖注入 | 绕过安全服务 |
| Core | `app/core/` | 数据结构、校验器、配置、安全值对象 | 持久化、外部 I/O |
| Services | `app/services/` | 策略裁决、计划生成、ToolGateway、状态管理 | Provider 级别的 HTTP/SQL 细节 |
| Workflows | `app/workflows/` | 编排顺序、条件路由、状态传递 | 重复定义策略/工具授权规则 |
| Tools | `app/tools/` | 工具契约和适配器 | 策略裁决 |
| RAG | `app/rag/` | 知识摄入、向量检索、证据生成 | 权限裁决 |
| Storage | `app/storage/` | SQLite/PostgreSQL 数据访问 | 用户响应生成 |
| LLM | `app/llm/` | Provider 契约、受保护适配器、响应生成 | 直接调用工具、最终策略裁决 |

### 主链路（`/api/chat`）

1. `app/api/chat.py` 创建 request/run ID，选择 manual 或 workflow 模式
2. Intent/Planner 生成候选 `ActionPlan`
3. `ActionPlanValidator` 校验结构合法性
4. `PolicyService` 评估所有权、租户、风险，返回 ALLOW/DENY/CONFIRM_REQUIRED/HUMAN_REQUIRED
5. 仅 ALLOW 进入 `ToolGateway`；CONFIRM_REQUIRED 创建 pending action
6. Trace/policy/tool/failure 记录通过 RuntimeStore 抽象层持久化

### 二次确认链路（`/api/confirm`）

1. 验证 pending_action 状态
2. 创建子 run（parent_run_id = 源 run_id）
3. `PolicyService` 重新复核
4. 通过 `ToolGateway` 执行
5. 标记 executed/cancelled

### 双轨模式（manual vs workflow）

项目同时存在手动链路（`app/api/chat.py` 直接调用 services）和 workflow 链路（通过 `app/workflows/chat_adapter.py` 编排）。两者通过 `SAFEAGENT_WORKFLOW_MODE` 切换。

- **manual**：`app/api/chat.py` 直接按顺序调用各个 service。
- **workflow + style engine**：`app/workflows/safeagent_workflow.py` 轻量编排。
- **workflow + langgraph engine**：`app/workflows/langgraph_chat_workflow.py` 真实 LangGraph 图编排，但默认不启用。

改动涉及主链路时，必须同时运行 `test_workflow_safety_regression.py` 确保双轨语义一致。

### ToolGateway（唯一工具入口）

`app/services/tool_gateway.py` 是所有工具执行的唯一通道：
- Allowlist 校验（`app/core/tool_allowlist.py`）
- 适配器分发（`app/tools/adapter.py` + `app/tools/registry.py`）
- 幂等性/日志边界
- 不负责业务授权（那是 PolicyService 的职责）

### RuntimeStore 抽象

`app/storage/runtime_store.py` 定义 `RuntimeStore` 协议，`app/storage/runtime_sqlite.py` 和 `app/storage/runtime_postgres.py` 分别实现。用于持久化 trace、policy log、tool log、failure log、pending action、checkpoint 等运行时事实。`app/services/repository_service.py` 提供统一的服务层仓库接口。

## 代码约定

- 文件/函数：`snake_case`；类型/接口：`PascalCase`；常量/环境变量：`UPPER_SNAKE_CASE`
- 四空格缩进，带类型注解
- 内部导入使用绝对路径 `from app...`
- `__init__.py` 选择性重导出集成面类型
- 测试文件：`tests/test_*.py`，函数：`test_*`
- 测试隔离：`tmp_path`、`monkeypatch`、FastAPI dependency overrides、注入 registry/provider
- 外部服务测试（PostgreSQL、LLM、Milvus）在环境变量缺失时自动 skip

## 重要文档索引

- `README.md` — 项目定位、快速启动、安全原则
- `docs/codebase/ARCHITECTURE.md` — 架构风格、系统流、分层矩阵、已知风险
- `docs/codebase/CONCERNS.md` — 风险清单、技术债、安全关注点（含 `[ASK USER]` 问题）
- `docs/codebase/STACK.md` — 技术栈、依赖、环境变量
- `docs/codebase/TESTING.md` — 测试策略、隔离方案
- `docs/codebase/CONVENTIONS.md` — 命名、导入、错误处理约定
- `docs/codebase/INTEGRATIONS.md` — 外部集成清单、数据存储、密钥处理
- `docs/codebase/STRUCTURE.md` — 目录结构、模块边界
- `docs/architecture/` — 产品架构、RAG 架构、Checkpoint/Resume 架构
- `.env.example` — 完整环境变量模板
