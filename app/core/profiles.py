import os
from dataclasses import dataclass

from app.core.env import load_env_files


PROFILE_DEV = "dev"
PROFILE_DEMO = "demo"
PROFILE_PROD = "prod"
VALID_PROFILES = {PROFILE_DEV, PROFILE_DEMO, PROFILE_PROD}


@dataclass(frozen=True)
class ProfileDefaults:
    workflow_mode: str
    workflow_engine: str
    llm_mode: str
    db_backend: str
    runtime_backend: str
    tool_backend: str


_PROFILE_DEFAULTS = {
    PROFILE_DEV: ProfileDefaults(
        workflow_mode="manual",
        workflow_engine="style",
        llm_mode="rule",
        db_backend="sqlite",
        runtime_backend="sqlite",
        tool_backend="mock",
    ),
    PROFILE_DEMO: ProfileDefaults(
        workflow_mode="workflow",
        workflow_engine="langgraph",
        llm_mode="rule",
        db_backend="postgres",
        runtime_backend="postgres",
        tool_backend="mock",
    ),
    PROFILE_PROD: ProfileDefaults(
        workflow_mode="workflow",
        workflow_engine="langgraph",
        llm_mode="real_llm",
        db_backend="postgres",
        runtime_backend="postgres",
        tool_backend="external_stub",
    ),
}


def get_active_profile() -> str:
    load_env_files()
    profile = os.getenv("SAFEAGENT_PROFILE", PROFILE_DEV).strip().lower()
    if profile not in VALID_PROFILES:
        return PROFILE_DEV
    return profile


def get_profile_defaults(profile: str | None = None) -> ProfileDefaults:
    selected_profile = profile or get_active_profile()
    if selected_profile not in VALID_PROFILES:
        selected_profile = PROFILE_DEV
    return _PROFILE_DEFAULTS[selected_profile]
