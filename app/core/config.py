import os
from dataclasses import dataclass

from app.core.env import load_env_files
from app.core.profiles import (
    PROFILE_DEV,
    VALID_PROFILES,
    get_active_profile,
    get_profile_defaults,
)
from app.storage.database_config import DB_BACKEND_SQLITE, VALID_DB_BACKENDS
from app.storage.runtime_config import (
    RUNTIME_BACKEND_SQLITE,
    VALID_RUNTIME_BACKENDS,
)


WORKFLOW_MODE_MANUAL = "manual"
WORKFLOW_MODE_WORKFLOW = "workflow"
VALID_WORKFLOW_MODES = {WORKFLOW_MODE_MANUAL, WORKFLOW_MODE_WORKFLOW}

WORKFLOW_ENGINE_STYLE = "style"
WORKFLOW_ENGINE_LANGGRAPH = "langgraph"
VALID_WORKFLOW_ENGINES = {WORKFLOW_ENGINE_STYLE, WORKFLOW_ENGINE_LANGGRAPH}

LLM_MODE_RULE = "rule"
LLM_MODE_MOCK_LLM = "mock_llm"
LLM_MODE_REAL_LLM = "real_llm"
VALID_LLM_MODES = {LLM_MODE_RULE, LLM_MODE_MOCK_LLM, LLM_MODE_REAL_LLM}

# v0.6-Tool-R1: 工具后端开关。默认 mock（4 个本地 Mock Adapter），
# external_stub 仅用于证明后续可把外部业务系统 adapter 接入 ToolGateway，
# 不发真实网络请求、不读取真实 API key。非法值回退 mock，避免误接实验性路径。
TOOL_BACKEND_MOCK = "mock"
TOOL_BACKEND_EXTERNAL_STUB = "external_stub"
VALID_TOOL_BACKENDS = {TOOL_BACKEND_MOCK, TOOL_BACKEND_EXTERNAL_STUB}


@dataclass(frozen=True)
class SafeAgentSettings:
    """应用运行配置。

    dev profile 默认保持 manual + SQLite。demo/prod profile 将成品主链路
    收敛到 PostgreSQL + workflow/langgraph；测试仍可通过未配置 profile 或
    显式覆盖继续使用 SQLite。
    """

    profile: str = PROFILE_DEV
    workflow_mode: str = WORKFLOW_MODE_MANUAL
    workflow_engine: str = WORKFLOW_ENGINE_STYLE
    llm_mode: str = LLM_MODE_RULE
    db_backend: str = DB_BACKEND_SQLITE
    database_url: str | None = None
    runtime_backend: str = RUNTIME_BACKEND_SQLITE
    runtime_database_url: str | None = None
    tool_backend: str = TOOL_BACKEND_MOCK


def get_settings() -> SafeAgentSettings:
    """读取运行配置。

    当前读取 SAFEAGENT_PROFILE、SAFEAGENT_WORKFLOW_MODE、SAFEAGENT_WORKFLOW_ENGINE、
    SAFEAGENT_LLM_MODE、SAFEAGENT_DB_BACKEND、SAFEAGENT_RUNTIME_BACKEND、
    SAFEAGENT_TOOL_BACKEND 和 DATABASE_URL。.env / .env.local 会自动加载，
    但不会覆盖进程里已经显式设置的环境变量。
    """
    load_env_files()
    profile = get_active_profile()
    if profile not in VALID_PROFILES:
        profile = PROFILE_DEV
    defaults = get_profile_defaults(profile)

    workflow_mode = os.getenv(
        "SAFEAGENT_WORKFLOW_MODE",
        defaults.workflow_mode,
    ).strip().lower()
    if workflow_mode not in VALID_WORKFLOW_MODES:
        workflow_mode = defaults.workflow_mode

    workflow_engine = os.getenv(
        "SAFEAGENT_WORKFLOW_ENGINE",
        defaults.workflow_engine,
    ).strip().lower()
    if workflow_engine not in VALID_WORKFLOW_ENGINES:
        workflow_engine = defaults.workflow_engine

    llm_mode = os.getenv(
        "SAFEAGENT_LLM_MODE",
        defaults.llm_mode,
    ).strip().lower()
    if llm_mode not in VALID_LLM_MODES:
        llm_mode = defaults.llm_mode

    db_backend = os.getenv("SAFEAGENT_DB_BACKEND", defaults.db_backend).strip().lower()
    if db_backend not in VALID_DB_BACKENDS:
        db_backend = defaults.db_backend

    runtime_backend = os.getenv(
        "SAFEAGENT_RUNTIME_BACKEND",
        defaults.runtime_backend,
    ).strip().lower()
    if runtime_backend not in VALID_RUNTIME_BACKENDS:
        runtime_backend = defaults.runtime_backend

    tool_backend = os.getenv(
        "SAFEAGENT_TOOL_BACKEND", defaults.tool_backend
    ).strip().lower()
    if tool_backend not in VALID_TOOL_BACKENDS:
        tool_backend = defaults.tool_backend

    return SafeAgentSettings(
        profile=profile,
        workflow_mode=workflow_mode,
        workflow_engine=workflow_engine,
        llm_mode=llm_mode,
        db_backend=db_backend,
        database_url=os.getenv("DATABASE_URL"),
        runtime_backend=runtime_backend,
        runtime_database_url=os.getenv("SAFEAGENT_RUNTIME_DATABASE_URL")
        or os.getenv("DATABASE_URL"),
        tool_backend=tool_backend,
    )
