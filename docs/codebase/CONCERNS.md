# Codebase Concerns

## Core Sections (Required)

### 1) Top Risks (Prioritized)

| Severity | Concern | Evidence | Impact | Suggested action |
|----------|---------|----------|--------|------------------|
| high | HTTP APIs have no application authentication/authorization dependency; user/session IDs are caller-supplied | `app/api/chat.py`, `app/api/confirm.py`, `app/api/observability.py` | identity spoofing and audit-data exposure if deployed publicly | add verified identity context, endpoint authorization and tenant scoping |
| high | Feishu webhook is a skeleton without signature verification or deduplication persistence | `app/api/channels/feishu.py`, `app/channels/feishu_adapter.py` | forged/replayed callbacks | verify signatures/timestamps and persist event IDs before production use |
| medium | Overlapping tool/action catalogs are maintained in multiple places | TODOs in `app/core/action_plan_validator.py`, `app/services/llm_output_guard.py` | validation/allowlist drift | introduce one immutable Action/Tool catalog |
| medium | Dependency versions and Python version are not pinned | `requirements.txt`, no runtime manifest | non-reproducible installs/supply-chain drift | add `pyproject.toml`/lock file and supported Python range |
| medium | No CI, lint, formatter, coverage or security scanning config | repository scan | regressions depend on local discipline | add CI quality gates and dependency/secret scanning |
| medium | Python 3.14 test run emits 48,063 dependency deprecation warnings | `python -m pytest -q` | real regressions can be buried in warning noise; future Python upgrades may break | pin supported Python/dependency versions and promote selected warnings to errors |

### 2) Technical Debt

| Debt item | Why it exists | Where | Risk if ignored | Suggested fix |
|-----------|---------------|-------|-----------------|---------------|
| Manual/workflow dual implementation | staged migration and rollback path | `app/api/chat.py`, `app/workflows/` | semantic drift | keep parity evaluations; converge orchestration when stable |
| Large persistence/workflow modules | broad runtime-state and transition surfaces | `runtime_postgres.py` (711 lines), `runtime_sqlite.py` (628), `confirm_workflow.py` (665), `safeagent_nodes.py` (555) | hard reviews and backend divergence | split by aggregate/transition and add contract suites |
| README reality drift | project evolved beyond v0.3 closure text | `README.md` versus `app/llm/`, `app/rag/vectorstores/milvus_store.py`, `app/api/checkpoints.py`, `console/` | misleading onboarding/resume claims | update feature matrix with production-readiness labels |

### 3) Security Concerns

| Risk | OWASP category | Evidence | Current mitigation | Gap |
|------|----------------|----------|--------------------|-----|
| Broken access control at API boundary | A01 | routers accept IDs directly and observability endpoints have no auth dependency | policy checks ownership for planned actions | transport identity, admin/read scopes, tenant filters |
| Webhook spoofing/replay | A07/A01 | Feishu endpoint accepts arbitrary JSON | adapter only normalizes/sanitizes | signature verification and durable dedupe |
| Sensitive trace/log data | A09/N/A | traces include messages/plans/results | `LoggingService` and observability redaction | centralized policy tests and retention/access controls |
| Dependency drift | A06 | unpinned requirements, no scanner | none found | lock, SBOM, automated vulnerability updates |

### 4) Performance and Scaling Concerns

| Concern | Evidence | Current symptom | Scaling risk | Suggested improvement |
|---------|----------|-----------------|-------------|-----------------------|
| SQLite is default state store | `app/core/profiles.py`, `app/storage/runtime_sqlite.py` | acceptable for dev | write contention and single-node state | use PostgreSQL for shared deployment and load-test transitions |
| Synchronous request path includes LLM/vector/database work | FastAPI sync endpoints; `openai_compatible_provider.py`; RAG modules | blocking worker per request | throughput/latency degradation | define time budgets; use async/client pools or bounded workers |
| No performance/load test configuration | scan output | no measured baseline | unknown capacity and tail latency | add chat/confirm/RAG load tests and SLOs |

### 5) Fragile/High-Churn Areas

| Area | Why fragile | Churn signal | Safe change strategy |
|------|-------------|-------------|----------------------|
| `app/core/config.py` | controls every backend/mode | highest recent app churn (4) | profile matrix tests for every change |
| `app/services/tool_gateway.py` | single execution/security boundary | recent churn (4) | preserve allowlist/idempotency/log assertions |
| chat/confirm services and APIs | cross-cut policy/state/audit semantics | multiple files at 2-3 changes | run manual/workflow and confirmation regression suites |

### 6) `[ASK USER]` Questions

1. [ASK USER] Is this repository intended to remain an interview/demo system, or should authentication, tenant isolation and webhook verification be treated as release blockers?
2. [ASK USER] Should MCP and Feishu remain contract skeletons, or is production transport integration part of the next milestone?
3. [ASK USER] Is the long-term source of truth for orchestration LangGraph, with manual mode retained only as rollback, or are both paths meant to remain first-class?

### 7) Evidence

- repository scan: TODOs, high-churn files, no CI/security/performance config
- `README.md`
- `app/api/chat.py`
- `app/api/observability.py`
- `app/channels/feishu_adapter.py`
- `app/core/action_plan_validator.py`
- `app/services/llm_output_guard.py`
- `app/storage/runtime_postgres.py`
