"""v0.8-Config: 环境变量加载与配置优先级测试。

验证：
- .env.local 能提供 PROFILE / DATABASE_URL / RUNTIME_DATABASE_URL
- 显式环境变量不会被 .env.local 覆盖
- pytest 下不会自动加载 .env.local
- demo profile 下 platform/runtime backend 默认 postgres
- dev profile 下默认 sqlite
"""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

import app.core.env as _env_mod
from app.core.env import load_env_files, _is_pytest_process
from app.core.profiles import (
    PROFILE_DEV,
    PROFILE_DEMO,
    get_active_profile,
    get_profile_defaults,
)
from app.core.config import get_settings, SafeAgentSettings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ── fixtures ──────────────────────────────────────────────────────────

_ENV_KEYS_TO_RESTORE = (
    "SAFEAGENT_PROFILE",
    "SAFEAGENT_DB_BACKEND",
    "SAFEAGENT_RUNTIME_BACKEND",
    "SAFEAGENT_WORKFLOW_MODE",
    "SAFEAGENT_WORKFLOW_ENGINE",
    "SAFEAGENT_LLM_MODE",
    "SAFEAGENT_TOOL_BACKEND",
    "DATABASE_URL",
    "SAFEAGENT_RUNTIME_DATABASE_URL",
)


@pytest.fixture(autouse=True)
def _isolate_test_env() -> Generator[None, None, None]:
    """每个测试前后保存/恢复关键环境变量，避免跨测试污染。"""
    saved = {k: os.environ.get(k) for k in _ENV_KEYS_TO_RESTORE}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── helpers ────────────────────────────────────────────────────────────


def _reset_env_files_flag() -> None:
    """重置 _ENV_FILES_LOADED 标志，使 load_env_files 可被再次调用。"""
    _env_mod._ENV_FILES_LOADED = False


def _write_dotenv_local(tmp_path: Path, **kwargs: str) -> Path:
    """在 tmp_path 下写入 .env.local 并返回路径。"""
    path = tmp_path / ".env.local"
    lines = [f"{k}={v}" for k, v in kwargs.items()]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── 基础 sanities ──────────────────────────────────────────────────────


def test_pytest_process_is_detected() -> None:
    """pytest 进程必须被识别为 pytest，确保 .env.local 不加载。"""
    assert _is_pytest_process() is True


def test_load_env_files_is_idempotent(monkeypatch: Any) -> None:
    """load_env_files 多次调用不会产生副作用。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: True)
    load_env_files()
    assert _env_mod._ENV_FILES_LOADED is True
    # 再次调用不应抛异常
    load_env_files()
    assert _env_mod._ENV_FILES_LOADED is True


# ── .env.local 加载 ────────────────────────────────────────────────────


def test_dotenv_local_provides_profile(monkeypatch: Any, tmp_path: Path) -> None:
    """.env.local 能提供 SAFEAGENT_PROFILE。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: False)
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)

    _write_dotenv_local(tmp_path, SAFEAGENT_PROFILE="demo")
    load_env_files()

    assert os.getenv("SAFEAGENT_PROFILE") == "demo"
    assert get_active_profile() == PROFILE_DEMO


def test_dotenv_local_provides_database_urls(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """.env.local 能提供 DATABASE_URL 和 SAFEAGENT_RUNTIME_DATABASE_URL。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: False)
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SAFEAGENT_RUNTIME_DATABASE_URL", raising=False)

    _write_dotenv_local(
        tmp_path,
        SAFEAGENT_PROFILE="demo",
        DATABASE_URL="postgresql://safeagent:safeagent_pwd@localhost:5432/safeagent_cs",
        SAFEAGENT_RUNTIME_DATABASE_URL="postgresql://safeagent:safeagent_pwd@localhost:5432/safeagent_cs",
    )
    load_env_files()

    assert "localhost:5432" in (os.getenv("DATABASE_URL") or "")
    assert "localhost:5432" in (os.getenv("SAFEAGENT_RUNTIME_DATABASE_URL") or "")


# ── 显式环境变量优先级 ────────────────────────────────────────────────


def test_explicit_env_var_not_overridden_by_dotenv_local(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """显式环境变量不会被 .env.local 覆盖。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: False)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "dev")
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "sqlite")

    _write_dotenv_local(
        tmp_path,
        SAFEAGENT_PROFILE="demo",
        SAFEAGENT_DB_BACKEND="postgres",
    )
    load_env_files()

    assert os.getenv("SAFEAGENT_PROFILE") == "dev"
    assert os.getenv("SAFEAGENT_DB_BACKEND") == "sqlite"


def test_runtime_database_url_falls_back_to_database_url(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """SAFEAGENT_RUNTIME_DATABASE_URL 未设置时，fallback 到 DATABASE_URL。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: False)
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.delenv("SAFEAGENT_RUNTIME_DATABASE_URL", raising=False)

    settings = get_settings()

    assert settings.runtime_database_url == "postgresql://u:p@host/db"


# ── pytest 隔离 ────────────────────────────────────────────────────────


def test_pytest_skips_dotenv_local(monkeypatch: Any, tmp_path: Path) -> None:
    """pytest 运行时 .env.local 不会被加载。"""
    _reset_env_files_flag()
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)

    _write_dotenv_local(tmp_path, SAFEAGENT_PROFILE="demo")
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)

    load_env_files()

    # pytest 模式应跳过 .env.local，PROFILE 保持原始值或默认 dev
    assert os.getenv("SAFEAGENT_PROFILE") is None


# ── Profile 默认值 ─────────────────────────────────────────────────────


def test_demo_profile_defaults_to_postgres(monkeypatch: Any) -> None:
    """demo profile 下 platform 和 runtime backend 默认 postgres。"""
    defaults = get_profile_defaults(PROFILE_DEMO)

    assert defaults.db_backend == "postgres"
    assert defaults.runtime_backend == "postgres"
    assert defaults.workflow_mode == "workflow"
    assert defaults.workflow_engine == "langgraph"
    assert defaults.llm_mode == "rule"
    assert defaults.tool_backend == "mock"


def test_dev_profile_defaults_to_sqlite() -> None:
    """dev profile 下 platform 和 runtime backend 默认 sqlite。"""
    defaults = get_profile_defaults(PROFILE_DEV)

    assert defaults.db_backend == "sqlite"
    assert defaults.runtime_backend == "sqlite"
    assert defaults.workflow_mode == "manual"
    assert defaults.tool_backend == "mock"


def test_prod_profile_defaults_to_real_llm_and_external_stub() -> None:
    """prod profile 默认启用真实 LLM 和外部工具 stub。"""
    defaults = get_profile_defaults("prod")

    assert defaults.llm_mode == "real_llm"
    assert defaults.tool_backend == "external_stub"


# ── get_settings 端到端 ────────────────────────────────────────────────


def test_get_settings_dev_defaults(monkeypatch: Any, tmp_path: Path) -> None:
    """get_settings 在 dev profile 下返回 SQLite 配置。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: True)
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SAFEAGENT_RUNTIME_DATABASE_URL", raising=False)
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    monkeypatch.delenv("SAFEAGENT_RUNTIME_BACKEND", raising=False)

    settings = get_settings()

    assert settings.profile == PROFILE_DEV
    assert settings.db_backend == "sqlite"
    assert settings.runtime_backend == "sqlite"
    assert settings.workflow_mode == "manual"
    assert isinstance(settings, SafeAgentSettings)


def test_get_settings_demo_with_dotenv_local(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """get_settings 在 demo profile + .env.local 下返回 PG 配置。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: False)
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SAFEAGENT_RUNTIME_DATABASE_URL", raising=False)
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    monkeypatch.delenv("SAFEAGENT_RUNTIME_BACKEND", raising=False)

    _write_dotenv_local(
        tmp_path,
        SAFEAGENT_PROFILE="demo",
        DATABASE_URL="postgresql://safeagent:safeagent_pwd@localhost:5432/safeagent_cs",
        SAFEAGENT_RUNTIME_DATABASE_URL="postgresql://safeagent:safeagent_pwd@localhost:5432/safeagent_cs",
    )
    load_env_files()

    settings = get_settings()

    assert settings.profile == PROFILE_DEMO
    assert settings.db_backend == "postgres"
    assert settings.runtime_backend == "postgres"
    assert settings.workflow_mode == "workflow"
    assert "localhost:5432" in (settings.database_url or "")


def test_get_settings_explicit_env_beats_dotenv_local(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """显式环境变量优先于 .env.local。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: False)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "dev")
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "sqlite")

    _write_dotenv_local(
        tmp_path,
        SAFEAGENT_PROFILE="demo",
        SAFEAGENT_DB_BACKEND="postgres",
    )
    load_env_files()

    settings = get_settings()

    assert settings.profile == PROFILE_DEV
    assert settings.db_backend == "sqlite"


def test_invalid_backend_falls_back_to_default(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """非法 backend 值回退到 profile 默认值。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: True)
    monkeypatch.delenv("SAFEAGENT_PROFILE", raising=False)
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "mongodb")

    settings = get_settings()

    assert settings.runtime_backend == "sqlite"  # dev default


def test_invalid_profile_falls_back_to_dev(monkeypatch: Any, tmp_path: Path) -> None:
    """非法 profile 值回退到 dev。"""
    _reset_env_files_flag()
    monkeypatch.setattr("app.core.env.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("app.core.env._is_pytest_process", lambda: True)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "staging")

    settings = get_settings()

    assert settings.profile == PROFILE_DEV
