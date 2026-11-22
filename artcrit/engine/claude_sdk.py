"""Real engine: the Claude Agent SDK on the user's Claude login (no API key).

See docs/spikes/2026-11-agent-sdk.md for the verified call shapes."""

import asyncio
import threading

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from claude_agent_sdk._errors import ResultError

from artcrit.engine.base import AgentResult, EngineError, ToolSpec, UsageLimitError

SERVER = "critic"
# The SDK rejects any single CLI message over 1 MB by default, and a tool result carrying one
# model-sized image (up to MODEL_MAX_B64 = 3.5 MB of base64) is a single message.
MAX_BUFFER_SIZE = 16 * 1024 * 1024


def _to_mcp_content(blocks: list[dict]) -> list[dict]:
    out = []
    for b in blocks:
        if b["type"] == "image":
            out.append({"type": "image", "data": b["png_b64"], "mimeType": "image/png"})
        else:
            out.append({"type": "text", "text": b["text"]})
    return out


def _wrap(spec: ToolSpec):
    @tool(spec.name, spec.description, spec.input_schema)
    async def handler(args):
        return {"content": _to_mcp_content(spec.handler(args))}

    return handler


class ClaudeSDKEngine:
    def run(self, system, prompt_text, images, tools, max_turns) -> AgentResult:
        return _run_sync(self._run(system, prompt_text, images, tools, max_turns))

    async def _run(self, system, prompt_text, images, tools, max_turns) -> AgentResult:
        server = create_sdk_mcp_server(SERVER, tools=[_wrap(t) for t in tools])
        opts = ClaudeAgentOptions(
            tools=[],
            mcp_servers={SERVER: server},
            strict_mcp_config=True,
            allowed_tools=[f"mcp__{SERVER}__{t.name}" for t in tools],
            permission_mode="dontAsk",
            setting_sources=[],
            system_prompt=system,
            max_turns=max_turns,
            max_buffer_size=MAX_BUFFER_SIZE,
        )
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b}} for b in images]
        content.append({"type": "text", "text": prompt_text})

        async def prompt():
            yield {"type": "user", "message": {"role": "user", "content": content}}

        last_text, trace, model, failure = "", [], "unknown", None
        try:
            async for msg in query(prompt=prompt(), options=opts):
                if isinstance(msg, RateLimitEvent) and msg.rate_limit_info.status == "rejected":
                    raise UsageLimitError(str(msg.rate_limit_info.rate_limit_type))
                if isinstance(msg, AssistantMessage):
                    model = msg.model or model
                    if msg.error in ("rate_limit", "billing_error"):
                        raise UsageLimitError(msg.error)
                    texts = [b.text for b in msg.content if isinstance(b, TextBlock)]
                    if texts:
                        last_text = "\n".join(texts)
                    trace += [{"tool": b.name.removeprefix(f"mcp__{SERVER}__"), "input": b.input}
                              for b in msg.content if isinstance(b, ToolUseBlock)]
                if isinstance(msg, ResultMessage):
                    if msg.is_error:
                        failure = msg
                    elif msg.result:
                        last_text = msg.result
        except ResultError as e:
            if e.subtype == "error_max_turns" or e.terminal_reason == "max_turns":
                return AgentResult(last_text, trace, model)  # parser decides; critic retries once
            if e.api_error_status == 429:
                raise UsageLimitError("rate_limit") from e
            raise EngineError(e.result or "; ".join(e.errors) or str(e)) from e
        if failure is not None and failure.subtype != "error_max_turns":
            raise EngineError(failure.result or "; ".join(failure.errors or []) or failure.subtype)
        return AgentResult(last_text, trace, model)


def _run_sync(coro):
    """Run a coroutine to completion even if the caller already has an event loop (e.g. FastAPI)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def target():
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as e:  # re-raised in caller thread
            box["error"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["value"]
