import os
from dataclasses import dataclass


WORKFLOW_MODE_MANUAL = "manual"
WORKFLOW_MODE_WORKFLOW = "workflow"
VALID_WORKFLOW_MODES = {WORKFLOW_MODE_MANUAL, WORKFLOW_MODE_WORKFLOW}


@dataclass(frozen=True)
class SafeAgentSettings:
    """应用运行配置。

    P0 默认保持 manual 主链路。workflow 模式只在显式配置后启用，
    非法配置值回退 manual，避免生产环境误开实验性编排路径。
    """

    workflow_mode: str = WORKFLOW_MODE_MANUAL


def get_settings() -> SafeAgentSettings:
    """读取运行配置。

    当前只读取 SAFEAGENT_WORKFLOW_MODE，后续可扩展为统一配置服务。
    """
    workflow_mode = os.getenv(
        "SAFEAGENT_WORKFLOW_MODE",
        WORKFLOW_MODE_MANUAL,
    ).strip().lower()
    if workflow_mode not in VALID_WORKFLOW_MODES:
        workflow_mode = WORKFLOW_MODE_MANUAL
    return SafeAgentSettings(workflow_mode=workflow_mode)

