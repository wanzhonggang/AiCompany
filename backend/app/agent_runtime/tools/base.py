from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolResult:
    success: bool = True
    data: Any = None
    error: Optional[str] = None

    def to_llm_format(self) -> str:
        if self.error:
            return f"Error: {self.error}"
        return str(self.data)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    requires_approval: bool = False
    timeout_seconds: int = 60

    @abstractmethod
    def get_spec(self) -> ToolSpec:
        ...

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        ...
