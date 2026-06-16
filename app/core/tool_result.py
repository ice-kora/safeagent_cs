from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolError:
    """工具调用失败的结构化错误信息。"""

    failure_type: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass
class ToolResult:
    """业务工具返回结果的统一结构。

    ToolResult 是 ToolGateway 之前的工具层契约。即使当前阶段还没有完整
    ToolGateway,Mock Tool 也必须先统一返回结构，避免后续编排层直接处理
    任意 dict。data 只放结构化且已脱敏的数据,summary 则提供给普通回复生成
    或 P0.5 的 LLMResponseGenerator 使用。
    """

    success: bool
    tool_name: str
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error_type: str | None = None
    safe_for_llm: bool = True
    error: ToolError | None = None

    def __post_init__(self) -> None:
        if self.error and not self.error_type:
            self.error_type = self.error.failure_type
        if self.data is None:
            self.data = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "data": self.data,
            "summary": self.summary,
            "error_type": self.error_type,
            "safe_for_llm": self.safe_for_llm,
            "error": self.error.to_dict() if self.error else None,
        }
