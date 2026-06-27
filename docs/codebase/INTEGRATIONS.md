# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type | Purpose | Auth model | Criticality | Evidence |
|--------|------|---------|------------|-------------|----------|
| OpenAI-compatible/DeepSeek endpoint | HTTPS API | intent/planning/response candidates | Bearer API key from environment | high when real LLM mode is enabled | `app/llm/openai_compatible_provider.py` |
| PostgreSQL | database | platform data and runtime audit/state | URL credentials from environment | high in demo/prod | `app/storage/postgres.py`, `app/storage/runtime_postgres.py` |
| Milvus | vector database | dense/hybrid RAG retrieval | URI; auth fields are not exposed in current template | medium | `app/rag/vectorstores/milvus_store.py`, `.env.demo.example` |
| BGE-M3/FlagEmbedding | local model/runtime | document/query embeddings and reranking | model identifier/cache path | medium | `app/rag/embeddings/bge_m3_embedder.py`, `app/rag/reranker.py` |
| Feishu | inbound webhook skeleton | normalize challenge/messages/card callbacks | `[TODO]` signature/token verification not implemented | low/skeleton | `app/channels/feishu_adapter.py`, `app/api/channels/feishu.py` |
| MCP | mock tool client skeleton | demonstrate adapter placement behind ToolGateway | none; local mock only | low/skeleton | `app/mcp/client.py`, `app/tools/mcp_adapter.py` |

### 2) Data Stores

| Store | Role | Access layer | Key risk | Evidence |
|-------|------|--------------|----------|----------|
| SQLite | default dev platform/runtime facts | `app/storage/db.py`, `SQLiteRuntimeStore` | local-file concurrency/multi-instance limits | `app/storage/runtime_sqlite.py` |
| PostgreSQL | demo/prod platform/runtime facts | repository + `PostgresRuntimeStore` | schema/transition parity with SQLite | `app/storage/postgres.py`, `app/storage/runtime_postgres.py` |
| In-memory vector store | deterministic dev/tests | RAG vector-store protocol | non-persistent and single-process | `app/rag/vectorstores/memory_vector_store.py` |
| Milvus | persistent vector search | `MilvusVectorStore` | external availability and collection/index lifecycle | `app/rag/vectorstores/milvus_store.py` |

### 3) Secrets and Credentials Handling

- Credentials come from process environment or ignored `.env.local`; public templates contain placeholders.
- LLM provider does not include API keys in response metadata; database URLs have a redaction helper.
- No secrets-manager integration or rotation procedure is present: `[TODO]`.

### 4) Reliability and Failure Behavior

- LLM HTTP calls have a configurable timeout and convert transport/payload failures to `LLMProviderError`; adapters can fall back depending on mode.
- Tool failures are represented as structured results and pass through `FailureHandler`; any retry returns through `ToolGateway`.
- No general circuit breaker is implemented. PostgreSQL/Milvus availability depends on their clients; production retry/backoff policy is `[TODO]`.

### 5) Observability for Integrations

- Agent runs expose trace, policy, tool-call and failure-log APIs, with payload sanitization.
- LLM adapters attach debug/fallback metadata; provider metadata excludes secrets.
- No Prometheus/APM/centralized log exporter or externally monitored SLO is configured.

### 6) Evidence

- `.env.example`
- `.env.demo.example`
- `app/llm/openai_compatible_provider.py`
- `app/storage/runtime_store.py`
- `app/rag/vectorstores/milvus_store.py`
- `app/api/observability.py`
- `app/mcp/client.py`
- `app/channels/feishu_adapter.py`
