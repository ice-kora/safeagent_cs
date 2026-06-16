from dataclasses import dataclass, field
from typing import Any


@dataclass
class SafeAgentError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
