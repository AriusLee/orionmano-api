"""Base skill class and types for the agentic AI system."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.context import AgentContext


class SkillStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class SkillParameter:
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class SkillResult:
    status: SkillStatus
    data: Any = None
    message: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    token_usage: int = 0

    @staticmethod
    def success(data: Any = None, message: str = "", artifacts: dict[str, Any] | None = None) -> SkillResult:
        return SkillResult(
            status=SkillStatus.SUCCESS,
            data=data,
            message=message,
            artifacts=artifacts or {},
        )

    @staticmethod
    def failed(message: str, data: Any = None) -> SkillResult:
        return SkillResult(
            status=SkillStatus.FAILED,
            data=data,
            message=message,
        )


class Skill(ABC):
    """Base class for all agent skills."""

    name: str = ""
    description: str = ""  # Used by the router to decide which skill to invoke
    parameters: list[SkillParameter] = []
    version: str = "1.0.0"

    def get_schema(self) -> dict:
        """Return OpenAI-compatible function/tool schema for this skill."""
        properties = {}
        required = []
        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @abstractmethod
    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        """Execute the skill with the given context and parameters."""
        ...

    def validate_params(self, **kwargs: Any) -> str | None:
        """Validate parameters. Returns error message or None if valid."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
            if param.enum and param.name in kwargs and kwargs[param.name] not in param.enum:
                return f"Invalid value for {param.name}: {kwargs[param.name]}. Must be one of {param.enum}"
        return None
