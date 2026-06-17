import os
from dataclasses import dataclass


WORKFLOW_MODE_MANUAL = "manual"
WORKFLOW_MODE_WORKFLOW = "workflow"
VALID_WORKFLOW_MODES = {WORKFLOW_MODE_MANUAL, WORKFLOW_MODE_WORKFLOW}

WORKFLOW_ENGINE_STYLE = "style"
WORKFLOW_ENGINE_LANGGRAPH = "langgraph"
VALID_WORKFLOW_ENGINES = {WORKFLOW_ENGINE_STYLE, WORKFLOW_ENGINE_LANGGRAPH}


@dataclass(frozen=True)
class SafeAgentSettings:
    """应用运行配置。

    P0 默认保持 manual 主链路。workflow 模式只在显式配置后启用，
    非法配置值回退 manual，避免生产环境误开实验性编排路径。
    """

    workflow_mode: str = WORKFLOW_MODE_MANUAL
    workflow_engine: str = WORKFLOW_ENGINE_STYLE


def get_settings() -> SafeAgentSettings:
    """读取运行配置。

    当前读取 SAFEAGENT_WORKFLOW_MODE 和 SAFEAGENT_WORKFLOW_ENGINE。
    engine 只在 workflow 模式下生效，非法值回退 style。
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

    return SafeAgentSettings(
        workflow_mode=workflow_mode,
        workflow_engine=workflow_engine,
    )
