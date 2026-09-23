from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel

from tools import errors
from tools.types import ToolConfirmation, ToolInvocation, ToolKind, ToolResult


class Tool(abc.ABC):
    name: str = "base_tool"
    description: str = "Base Tool"
    kind: ToolKind = ToolKind.READ

    def __init__(self) -> None:
        pass

    @property
    def schema(self) -> dict[str, Any] | type[BaseModel]:
        raise NotImplementedError("Subclasses must implement the schema property.")

    @abc.abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        pass

    def validate_params(self, params: dict[str, Any]) -> bool:
        schema = self.schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                schema(**params)
                return True
            except Exception:
                return False
        elif isinstance(schema, dict):
            return all(key in params for key in schema.keys())
        else:
            raise ValueError("Schema must be a Pydantic model or a dictionary.")

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return self.kind in {ToolKind.WRITE, ToolKind.SHELL, ToolKind.NETWORK, ToolKind.MEMORY}

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        if not self.is_mutating(invocation.params):
            return None

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=errors.mutating_confirmation(self.name),
        )

    def to_dict(self) -> dict[str, Any]:
        if isinstance(self.schema, dict):
            properties = self.schema
            required = list(self.schema.keys())
        else:
            json_schema = self.schema.model_json_schema()
            properties = json_schema.get("properties", {})
            required = json_schema.get("required", [])

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
