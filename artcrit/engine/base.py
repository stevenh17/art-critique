"""The one interface every agent call goes through, so the engine can be swapped later."""

from dataclasses import dataclass, field
from typing import Callable, Protocol

ToolResult = list[dict]  # blocks: {"type": "text", "text": ...} or {"type": "image", "png_b64": ...}


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], ToolResult]


@dataclass
class AgentResult:
    text: str
    tool_trace: list[dict] = field(default_factory=list)
    model: str = "unknown"


class UsageLimitError(Exception):
    """The Claude plan's usage limit was reached; retry later."""


class AgentEngine(Protocol):
    def run(
        self, system: str, prompt_text: str, images: list[str], tools: list[ToolSpec], max_turns: int
    ) -> AgentResult:
        """Run one bounded agent. `images` are base64 PNGs, sent before the prompt text."""
        ...
