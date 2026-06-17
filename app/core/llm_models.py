from dataclasses import dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.0"


class GuardStatus(str, Enum):
    """LLM 输出或回复草稿的校验状态枚举。

    本文件只定义数据契约，不实现 Guard 逻辑；具体校验会在后续
    LLMOutputGuard / LLMResponseGuard 阶段实现。
    """

    VALID = "VALID"
    INVALID_JSON = "INVALID_JSON"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    FORBIDDEN_OUTPUT = "FORBIDDEN_OUTPUT"
    BLOCKED = "BLOCKED"


class Mode(str, Enum):
    """P0.5 支持的运行模式。"""

    RULE = "rule"
    HYBRID = "hybrid"
    LLM = "llm"
    LLM_STRICT = "llm_strict"


class FallbackReasonCode(str, Enum):
    """模式降级和 Guard 拦截的稳定机器码。"""

    NO_API_KEY = "NO_API_KEY"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    INVALID_JSON = "INVALID_JSON"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    FORBIDDEN_OUTPUT = "FORBIDDEN_OUTPUT"
    RESPONSE_GUARD_BLOCKED = "RESPONSE_GUARD_BLOCKED"
    LLM_STRICT_DISABLED = "LLM_STRICT_DISABLED"
    UNKNOWN = "UNKNOWN"


@dataclass
class LLMIntentResult:
    """LLM 生成的候选意图结果。

    该结构只表示模型输出的候选理解结果，不代表系统已经接受该意图。
    后续必须经过 LLMOutputGuard 和主链路校验。
    """

    intent: str
    confidence: float
    entities: dict[str, str] = field(default_factory=dict)
    raw_user_message_hash: str | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass
class LLMActionPlanCandidate:
    """LLM 生成的候选 ActionPlan。

    该结构不能直接进入工具执行；它只是 LLM Planner 的候选输出。
    后续仍必须转换为内部 ActionPlan，并经过 ActionPlanValidator 和 PolicyService。
    """

    intent: str
    action: str
    target_type: str | None
    target_id: str | None
    tool_name: str | None
    reason: str
    confidence: float
    tool_args: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


@dataclass
class LLMResponseDraft:
    """LLM 生成的回复草稿。

    草稿不能直接返回给用户，必须经过 LLMResponseGuard 检查，确保没有
    改写系统裁决、编造结果或泄露敏感信息。
    """

    response_text: str
    referenced_status: str
    referenced_policy_decision: str | None
    referenced_tool_result_success: bool | None
    safe_for_user_candidate: bool
    schema_version: str = SCHEMA_VERSION


@dataclass
class LLMGuardResult:
    """LLM 输出校验结果的数据契约。"""

    guard_status: str
    fallback_required: bool
    sanitized_payload: dict[str, Any] | None = None
    blocked_reason: str | None = None
    confidence: float | None = None
    schema_version: str = SCHEMA_VERSION


@dataclass
class ModeDecision:
    """ModeRouter 的结构化决策结果。

    Trace 应记录 requested_mode、effective_mode 和 fallback_reason_code，
    这样企业环境里可以稳定排查 LLM 降级原因。
    """

    requested_mode: str
    effective_mode: str
    intent_source: str
    planner_source: str
    fallback_required: bool
    llm_enabled: bool
    fallback_reason_code: str | None = None
    fallback_reason: str | None = None
    schema_version: str = SCHEMA_VERSION
