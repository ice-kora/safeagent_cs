# Architecture

## Core Sections (Required)

### 1) Architectural Style

- Primary style: layered service architecture with a policy-enforcement gateway and optional workflow orchestration.
- Classification evidence: HTTP routers wire services; workflow nodes reuse those services; persistence and integrations sit behind protocols/adapters.
- Primary constraints: LLM/RAG only produce candidates or evidence; every action plan is validated and policy-checked; every tool call passes through `ToolGateway`.

### 2) System Flow

```text
POST /api/chat -> Intent/Planner -> ActionPlanValidator -> PolicyService
  -> ALLOW: ToolGateway -> ToolAdapter -> FailureHandler -> response
  -> CONFIRM_REQUIRED: PendingAction + Checkpoint -> POST /api/confirm -> policy re-check -> ToolGateway
  -> DENY/HUMAN_REQUIRED: safe response without tool execution
```

1. `app/api/chat.py` creates request/run IDs and chooses manual or workflow mode.
2. classifier and planner create a candidate `ActionPlan`; validator rejects malformed/unknown actions before policy evaluation.
3. `PolicyService` evaluates ownership, tenant/risk and returns ALLOW, DENY, CONFIRM_REQUIRED, or HUMAN_REQUIRED.
4. Only ALLOW reaches `ToolGateway`; confirmation persists a pending action and checkpoint without executing the tool.
5. `/api/confirm` validates identity/status, creates a child run, rechecks policy, and executes through the gateway.
6. trace, policy, tool, failure and pending/checkpoint facts are persisted through a runtime-store abstraction.

### 3) Layer/Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| API | transport, Pydantic input, DI | bypass safety services | `app/api/chat.py`, `app/api/confirm.py` |
| Validator/Policy | plan validity and deterministic authorization/risk | tool execution | `app/core/action_plan_validator.py`, `app/services/policy_service.py` |
| Workflow | ordering, state, branch routing | redefine policy/tool rules | `app/workflows/safeagent_nodes.py`, `app/workflows/langgraph_chat_workflow.py` |
| ToolGateway | allowlist, adapter dispatch, idempotency/logging boundary | decide business authorization | `app/services/tool_gateway.py` |
| RAG | retrieve/rerank evidence and safe summaries | grant permissions | `app/rag/rag_service.py`, `app/tools/knowledge_tool.py` |
| Storage | platform and runtime persistence | workflow decisions | `app/storage/runtime_store.py`, `app/storage/postgres.py` |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Repository/store abstraction | `app/services/repository_service.py`, `app/storage/runtime_store.py` | switch SQLite/PostgreSQL without changing services |
| Adapter/registry | `app/tools/adapter.py`, `app/tools/registry.py`, `app/llm/registry.py` | isolate providers and tool implementations |
| Strategy/config profile | `app/core/profiles.py`, `app/core/config.py` | deterministic dev/demo/prod behavior |
| Dependency injection | FastAPI `Depends` in `app/api/` | replace services in tests and keep HTTP wiring explicit |
| State machine/workflow | `app/workflows/`, pending actions/checkpoints | model controlled branching and resumable human confirmation |

### 5) Known Architectural Risks

- Manual and workflow chat paths coexist, creating behavioral-drift risk despite regression tests.
- `ActionPlanValidator` and LLM/tool code maintain overlapping action/tool catalogs (explicit TODO), risking inconsistent allowlists.
- Runtime SQLite/PostgreSQL and confirm workflow implementations are large and can accumulate duplicated transition logic.

### 6) Evidence

- `README.md`
- `app/main.py`
- `app/api/chat.py`
- `app/api/confirm.py`
- `app/services/policy_service.py`
- `app/services/tool_gateway.py`
- `app/workflows/langgraph_chat_workflow.py`
- `app/storage/runtime_store.py`
