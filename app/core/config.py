import os
from dataclasses import dataclass

from app.storage.database_config import DB_BACKEND_SQLITE, VALID_DB_BACKENDS


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

    P0 默认保持 manual 主链路。workflow 模式只在显式配置后启用，
    非法配置值回退 manual，避免生产环境误开实验性编排路径。
    """

    workflow_mode: str = WORKFLOW_MODE_MANUAL
    workflow_engine: str = WORKFLOW_ENGINE_STYLE
    llm_mode: str = LLM_MODE_RULE
    db_backend: str = DB_BACKEND_SQLITE
    database_url: str | None = None
    tool_backend: str = TOOL_BACKEND_MOCK


def get_settings() -> SafeAgentSettings:
    """读取运行配置。

    当前读取 SAFEAGENT_WORKFLOW_MODE、SAFEAGENT_WORKFLOW_ENGINE、
    SAFEAGENT_LLM_MODE、SAFEAGENT_DB_BACKEND、SAFEAGENT_TOOL_BACKEND
    和 DATABASE_URL。engine 只在 workflow 模式下生效，非法值回退 style。
    llm_mode 默认 rule，非法值回退 rule。tool_backend 默认 mock，
    非法值回退 mock。
    """
    workflow_mode = os.getenv(
        "SAFEAGENT_WORKFLOW_MODE",
        WORKFLOW_MODE_MANUAL,
    ).strip().lower()
    if workflow_mode not in VALID_WORKFLOW_MODES:
        workflow_mode = WORKFLOW_MODE_MANUAL

    workflow_engine = os.getenv(
        "SAFEAGENT_WORKFLOW_ENGINE",
        WORKFLOW_ENGINE_STYLE,
    ).strip().lower()
    if workflow_engine not in VALID_WORKFLOW_ENGINES:
        workflow_engine = WORKFLOW_ENGINE_STYLE

    llm_mode = os.getenv(
        "SAFEAGENT_LLM_MODE",
        LLM_MODE_RULE,
    ).strip().lower()
    if llm_mode not in VALID_LLM_MODES:
        llm_mode = LLM_MODE_RULE

    db_backend = os.getenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_SQLITE).strip().lower()
    if db_backend not in VALID_DB_BACKENDS:
        db_backend = DB_BACKEND_SQLITE

    tool_backend = os.getenv(
        "SAFEAGENT_TOOL_BACKEND", TOOL_BACKEND_MOCK
    ).strip().lower()
    if tool_backend not in VALID_TOOL_BACKENDS:
        tool_backend = TOOL_BACKEND_MOCK

    return SafeAgentSettings(
        workflow_mode=workflow_mode,
        workflow_engine=workflow_engine,
        llm_mode=llm_mode,
        db_backend=db_backend,
        database_url=os.getenv("DATABASE_URL"),
        tool_backend=tool_backend,
    )
