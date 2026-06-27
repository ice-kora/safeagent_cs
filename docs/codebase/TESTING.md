# Testing Patterns

## Core Sections (Required)

### 1) Test Stack and Commands

- Primary test framework: pytest (declared without a version pin).
- Assertion/mocking tools: plain `assert`, `pytest.raises`, `monkeypatch`, `tmp_path`, FastAPI `TestClient`, dependency overrides, injected fake providers/adapters.

```bash
python -m pytest
python -m pytest tests/test_policy_service.py tests/test_tool_gateway.py
python -m pytest tests/test_chat_api.py tests/test_confirm_flow_integration.py
# no coverage command is configured
```

### 2) Test Layout

- Tests are centralized under `tests/`; evaluation cases also exist under `tests/evals/`.
- Files/functions follow `test_*.py` / `test_*`; shared setup is in `tests/conftest.py`.
- Optional real PostgreSQL/LLM smoke tests skip when required environment variables/services are absent.

### 3) Test Scope Matrix

| Scope | Covered? | Typical target | Notes |
|-------|----------|----------------|-------|
| Unit | yes | validators, policy, adapters, RAG metrics | deterministic mocks/temp databases |
| Integration | yes | chat/confirm APIs, ToolGateway, SQLite/PostgreSQL boundaries, workflow parity | FastAPI TestClient and optional external DB |
| E2E | partial | product smoke, demo, console static contract | local composition; no browser-driven or live third-party E2E |

### 4) Mocking and Isolation Strategy

- Dependencies are replaced through constructor injection, registries, FastAPI overrides and `monkeypatch`; filesystem/database tests use `tmp_path`.
- Dev RAG uses in-memory/mock embedding; MCP and business tools have mock adapters; real external tests are opt-in.
- Common failure mode: profile/environment state can alter selected backends, so tests explicitly set/delete variables and shared setup resets local state.

### 5) Coverage and Quality Signals

- Coverage tool + threshold: `[TODO]` not configured.
- Current reported coverage: `[TODO]`.
- Repository scan found 89 Python test files. Current local baseline: `544 passed, 15 skipped` in 44.60s; skips are environment-gated external-service paths.
- Python 3.14.2 produced 48,063 third-party deprecation warnings, predominantly from pytest-asyncio/FastAPI/Starlette coroutine checks.
- Gaps: live Feishu authentication, real MCP transport, production external tools, and multi-instance/failure-injection tests.

### 6) Evidence

- `requirements.txt`
- `tests/conftest.py`
- `tests/test_chat_api.py`
- `tests/test_confirm_flow_integration.py`
- `tests/test_workflow_safety_regression.py`
- `tests/test_postgres_backend_optional.py`
- `tests/test_real_llm_mode_smoke.py`
- terminal: `python -m pytest -q` on 2026-06-21
