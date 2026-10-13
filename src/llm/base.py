"""Types shared by LLM provider clients."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    """A requested function call returned by a chat model."""

    id: str
    name: str
    arguments: str


@dataclass
class ChatResponse:
    """Normalized provider response containing function calls."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    content: str | None = None


class LLMClient(Protocol):
    """Contract for a provider that supports OpenAI-style function calling."""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResponse:
        """Return the next model response for a conversation."""
