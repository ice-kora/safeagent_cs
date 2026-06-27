# Coding Conventions

## Core Sections (Required)

### 1) Naming Rules

| Item | Rule | Example | Evidence |
|------|------|---------|----------|
| Files | `snake_case.py` | `pending_action_service.py` | `app/services/` |
| Functions/methods | `snake_case`; leading underscore for module-private helpers | `get_settings`, `_build_chat_tool_args` | `app/core/config.py`, `app/api/chat.py` |
| Types/interfaces | `PascalCase`; protocol interfaces where useful | `PolicyService`, `RuntimeStore` | `app/services/policy_service.py`, `app/storage/runtime_store.py` |
| Constants/env vars | uppercase snake case | `WORKFLOW_MODE_MANUAL`, `SAFEAGENT_PROFILE` | `app/core/config.py`, `.env.example` |

### 2) Formatting and Linting

- Formatter: `[TODO]` no formatter/config found.
- Linter: `[TODO]` no linter/config found.
- Observable style: four-space indentation, type annotations, dataclasses/protocols, docstrings on public/service boundaries.
- Run commands: none configured for formatting/linting.

### 3) Import and Module Conventions

- Standard-library imports precede third-party and `app.*` imports, separated by blank lines in representative modules.
- Internal imports are absolute (`from app...`), not relative.
- Package `__init__.py` files selectively re-export integration-facing types; there is no repository-wide barrel policy.

### 4) Error and Logging Conventions

- Core/provider layers raise typed exceptions; APIs map missing resources/state errors to `HTTPException`; tool calls return structured `ToolResult`/`ToolError`; workflow failures are converted to safe terminal states.
- `LoggingService` writes structured event names and context; trace/policy/tool/failure records carry run/request/session identifiers where applicable.
- Sensitive payloads are passed through `LoggingService.sanitize_payload`; observability adds card/system-prompt/address redaction; LLM response contracts reject secret-like keys.

### 5) Testing Conventions

- Tests live in `tests/` and use `test_*.py` plus `test_*` functions.
- `tmp_path`, `monkeypatch`, FastAPI dependency overrides, injected registries/providers, and optional environment-gated PostgreSQL/LLM tests isolate dependencies.
- Coverage expectation: `[TODO]` no coverage tool or threshold configured.

### 6) Evidence

- `app/api/chat.py`
- `app/services/logging_service.py`
- `app/core/errors.py`
- `app/core/tool_result.py`
- `app/llm/provider.py`
- `tests/conftest.py`
- repository scan (no lint/format configuration found)
