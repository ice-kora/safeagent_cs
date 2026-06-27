# Codebase Structure

## Core Sections (Required)

### 1) Top-Level Map

| Path | Purpose | Evidence |
|------|---------|----------|
| `app/` | FastAPI application, safety kernel, workflow, RAG, tools, storage | `app/main.py`, package layout |
| `tests/` | pytest unit, integration, regression, and optional external-service smoke tests | `tests/` |
| `console/` | static operator/customer console mounted by FastAPI | `console/index.html`, `app/main.py` |
| `docs/` | design, architecture, acceptance, knowledge corpus, runbooks | `docs/architecture/`, `docs/knowledge/` |
| `scripts/` | demo seeding and knowledge-ingestion utilities | `scripts/` |
| `demo/` | local runnable demonstrations | `demo/demo_v03_safeagent.py` |
| `data/` | local SQLite/runtime artifacts | `data/safeagent.db` |

### 2) Entry Points

- Main runtime entry: `app/main.py` (`uvicorn app.main:app`).
- Secondary entry points: `demo/` scripts and data/knowledge scripts under `scripts/`.
- API routers are registered in `app/main.py`; profile/environment configuration selects manual vs workflow and concrete backends.

### 3) Module Boundaries

| Boundary | What belongs here | What must not be here |
|----------|-------------------|------------------------|
| `app/api/` | request models, dependency wiring, HTTP responses | direct adapter/tool execution |
| `app/core/` | plans, policy/risk/security value objects, validators, configuration | persistence and external I/O |
| `app/services/` | policy, planning, gateway, pending action, trace and failure orchestration | provider-specific HTTP/SQL details |
| `app/workflows/` | manual/LangGraph sequencing and workflow state | duplicated policy or tool authorization rules |
| `app/tools/` | tool contracts and adapters | policy decisions |
| `app/rag/` | ingestion, embedding, retrieval, evidence and evaluation | authorization decisions |
| `app/storage/` | SQLite/PostgreSQL schemas and stores | user-facing response generation |
| `app/llm/` | provider contracts, guarded adapters, response generation | direct tools or final policy decisions |

### 4) Naming and Organization Rules

- Python files/directories use `snake_case`; types use `PascalCase`.
- The source tree is predominantly layer-oriented, with domain-specific subpackages inside RAG and integrations.
- Imports are absolute from `app.*`; no path aliases or barrel module policy is configured.

### 5) Evidence

- `docs/codebase/.codebase-scan.txt` (used during discovery, removed after documentation generation)
- `app/main.py`
- `app/api/chat.py`
- `app/workflows/langgraph_chat_workflow.py`
- `app/storage/runtime_store.py`
