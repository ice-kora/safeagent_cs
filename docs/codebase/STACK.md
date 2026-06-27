# Technology Stack

## Core Sections (Required)

### 1) Runtime Summary

| Area | Value | Evidence |
|------|-------|----------|
| Primary language | Python | `app/main.py` |
| Runtime + version | Python 3.14.2 in the inspected environment; the repository does not pin a Python version | terminal `python --version`; no `pyproject.toml`/runtime pin |
| Package manager | pip with a flat requirements file | `requirements.txt`, `README.md` |
| Module/build system | Python packages imported from repository root; no build configuration | `app/main.py`, repository root |

### 2) Production Frameworks and Dependencies

Dependency versions are mostly unpinned, so exact deployed versions are `[TODO]`.

| Dependency | Version | Role in system | Evidence |
|------------|---------|----------------|----------|
| FastAPI / Uvicorn | unpinned | HTTP API and ASGI server | `requirements.txt`, `app/main.py` |
| LangGraph | unpinned | Optional workflow graph engine | `requirements.txt`, `app/workflows/langgraph_chat_workflow.py` |
| psycopg | unpinned | PostgreSQL platform/runtime persistence | `requirements.txt`, `app/storage/postgres.py`, `app/storage/runtime_postgres.py` |
| pymilvus | unpinned | Milvus vector store | `requirements.txt`, `app/rag/vectorstores/milvus_store.py` |
| FlagEmbedding | unpinned | BGE-M3 embeddings/reranking | `requirements.txt`, `app/rag/embeddings/bge_m3_embedder.py`, `app/rag/reranker.py` |
| pypdf/lxml/python-docx/openpyxl | mostly unpinned | Multi-format knowledge ingestion | `requirements.txt`, `app/rag/loaders/` |
| urllib (stdlib) | Python runtime | OpenAI-compatible Chat Completions HTTP transport | `app/llm/openai_compatible_provider.py` |

### 3) Development Toolchain

| Tool | Purpose | Evidence |
|------|---------|----------|
| pytest | unit/integration/smoke tests | `requirements.txt`, `tests/` |
| FastAPI TestClient/httpx | API testing | `requirements.txt`, `tests/test_chat_api.py` |
| Linter/formatter | `[TODO]` none configured in repository root | scan output |

### 4) Key Commands

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
python -m pytest
```

There is no build or lint command configured.

### 5) Environment and Config

- Config sources: `.env`, `.env.local`, `.env.example`, `.env.demo.example`, process environment, `app/core/config.py`, `app/core/profiles.py`.
- Important variables: `SAFEAGENT_PROFILE`, workflow/LLM/tool/backend variables, PostgreSQL URLs, Milvus settings, and `SAFEAGENT_LLM_*`/compatible `DEEPSEEK_*` credentials.
- Profiles: dev defaults to manual + SQLite + mock; demo to LangGraph + PostgreSQL + Milvus; prod to LangGraph + PostgreSQL + real LLM + external tool stub.
- No container or CI configuration is committed; external PostgreSQL/Milvus processes must be supplied separately.

### 6) Evidence

- `requirements.txt`
- `.env.example`
- `.env.demo.example`
- `app/core/config.py`
- `app/core/profiles.py`
- `app/main.py`
