"""Scripted engine for tests: each run() pops the next step and records its inputs."""

from typing import Callable

from artcrit.engine.base import AgentResult, ToolSpec


class FakeEngine:
    def __init__(self, script: list[Callable[[list[ToolSpec]], AgentResult]]):
        self.script = list(script)
        self.calls: list[dict] = []

    def run(self, system, prompt_text, images, tools, max_turns) -> AgentResult:
        self.calls.append(
            {"system": system, "prompt_text": prompt_text, "images": images, "tools": tools, "max_turns": max_turns}
        )
        assert self.script, "FakeEngine script exhausted"
        return self.script.pop(0)(tools)
