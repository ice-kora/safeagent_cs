from app.core.config import (
    LLM_MODE_REAL_LLM,
    LLM_MODE_RULE,
    TOOL_BACKEND_EXTERNAL_STUB,
    TOOL_BACKEND_MOCK,
    WORKFLOW_ENGINE_LANGGRAPH,
    WORKFLOW_ENGINE_STYLE,
    WORKFLOW_MODE_MANUAL,
    WORKFLOW_MODE_WORKFLOW,
    get_settings,
)
from app.storage.database_config import (
    DB_BACKEND_POSTGRES,
    DB_BACKEND_SQLITE,
    get_database_settings,
)
from app.storage.runtime_config import (
    RUNTIME_BACKEND_POSTGRES,
    RUNTIME_BACKEND_SQLITE,
    get_runtime_database_settings,
)


ENV_KEYS = (
    "SAFEAGENT_PROFILE",
    "SAFEAGENT_WORKFLOW_MODE",
    "SAFEAGENT_WORKFLOW_ENGINE",
    "SAFEAGENT_LLM_MODE",
    "SAFEAGENT_DB_BACKEND",
    "SAFEAGENT_RUNTIME_BACKEND",
    "SAFEAGENT_TOOL_BACKEND",
    "SAFEAGENT_RUNTIME_DATABASE_URL",
    "DATABASE_URL",
)


def _clear_profile_env(monkeypatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_dev_profile_keeps_test_friendly_defaults(monkeypatch) -> None:
    _clear_profile_env(monkeypatch)

    settings = get_settings()

    assert settings.profile == "dev"
    assert settings.workflow_mode == WORKFLOW_MODE_MANUAL
    assert settings.workflow_engine == WORKFLOW_ENGINE_STYLE
    assert settings.llm_mode == LLM_MODE_RULE
    assert settings.db_backend == DB_BACKEND_SQLITE
    assert settings.runtime_backend == RUNTIME_BACKEND_SQLITE
    assert settings.tool_backend == TOOL_BACKEND_MOCK
    assert get_database_settings().backend == DB_BACKEND_SQLITE
    assert get_runtime_database_settings().backend == RUNTIME_BACKEND_SQLITE


def test_demo_profile_defaults_to_pg_ready_workflow(monkeypatch) -> None:
    _clear_profile_env(monkeypatch)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "demo")

    settings = get_settings()

    assert settings.profile == "demo"
    assert settings.workflow_mode == WORKFLOW_MODE_WORKFLOW
    assert settings.workflow_engine == WORKFLOW_ENGINE_LANGGRAPH
    assert settings.llm_mode == LLM_MODE_RULE
    assert settings.db_backend == DB_BACKEND_POSTGRES
    assert settings.runtime_backend == RUNTIME_BACKEND_POSTGRES
    assert settings.tool_backend == TOOL_BACKEND_MOCK
    assert get_database_settings().backend == DB_BACKEND_POSTGRES
    assert get_runtime_database_settings().backend == RUNTIME_BACKEND_POSTGRES


def test_prod_profile_defaults_to_guarded_real_llm_and_controlled_tools(
    monkeypatch,
) -> None:
    _clear_profile_env(monkeypatch)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "prod")

    settings = get_settings()

    assert settings.profile == "prod"
    assert settings.workflow_mode == WORKFLOW_MODE_WORKFLOW
    assert settings.workflow_engine == WORKFLOW_ENGINE_LANGGRAPH
    assert settings.llm_mode == LLM_MODE_REAL_LLM
    assert settings.db_backend == DB_BACKEND_POSTGRES
    assert settings.runtime_backend == RUNTIME_BACKEND_POSTGRES
    assert settings.tool_backend == TOOL_BACKEND_EXTERNAL_STUB


def test_profile_defaults_can_be_overridden(monkeypatch) -> None:
    _clear_profile_env(monkeypatch)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "demo")
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_SQLITE)
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", RUNTIME_BACKEND_SQLITE)
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", WORKFLOW_MODE_MANUAL)

    settings = get_settings()

    assert settings.workflow_mode == WORKFLOW_MODE_MANUAL
    assert settings.db_backend == DB_BACKEND_SQLITE
    assert settings.runtime_backend == RUNTIME_BACKEND_SQLITE
    assert get_database_settings().backend == DB_BACKEND_SQLITE
    assert get_runtime_database_settings().backend == RUNTIME_BACKEND_SQLITE
