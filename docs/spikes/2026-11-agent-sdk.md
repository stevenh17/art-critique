# Spike: Agent SDK on a Claude Pro login (2026-11-20)

**Result: works. No API key needed.** `claude-agent-sdk` 0.2.186 bundles Claude Code 2.1.329 (`claude_agent_sdk/_bundled/claude`), and that bundled copy uses the machine's existing Claude login. The run reported a `five_hour` subscription rate-limit window, not API billing. The `claude -p` fallback isn't needed.

Script: `spikes/agent_sdk_spike.py` (run with `env -u ANTHROPIC_API_KEY .venv/bin/python spikes/agent_sdk_spike.py`).

## What was verified
- The model described an image sent in the prompt.
- It called two in-process custom tools in order and read an image returned by a tool.
- It made no built-in tool calls.
- With `max_turns=1` it stopped with `ResultMessage.subtype == "error_max_turns"`; the SDK then raises `claude_agent_sdk._errors.ResultError` once iteration ends.
- Model reported: `claude-opus-5-5` (`AssistantMessage.model`).

## Exact usage
```python
from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, RateLimitEvent, ResultMessage,
    TextBlock, ToolUseBlock, create_sdk_mcp_server, query, tool)

@tool("name", "description", {"arg": str})          # or a JSON Schema dict
async def handler(args): return {"content": [
    {"type": "text", "text": "..."},
    {"type": "image", "data": "<b64 png>", "mimeType": "image/png"}]}

server = create_sdk_mcp_server("critic", tools=[handler])
opts = ClaudeAgentOptions(
    tools=[],                         # disables ALL built-in tools
    mcp_servers={"critic": server}, strict_mcp_config=True,
    allowed_tools=["mcp__critic__name"],   # tool names are mcp__<server>__<tool>
    permission_mode="dontAsk", setting_sources=[],   # ignore user/project settings
    system_prompt="...", max_turns=N)

async def prompt():   # images go in the prompt via a streamed user message
    yield {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        {"type": "text", "text": "..."}]}}

async for msg in query(prompt=prompt(), options=opts): ...
```

## Signals
- Final text: the last `TextBlock`s of the last `AssistantMessage`, or `ResultMessage.result`.
- Usage limit: `RateLimitEvent.rate_limit_info.status == "rejected"`, or `AssistantMessage.error == "rate_limit"`. Map either to `UsageLimitError`.
- `ResultMessage.total_cost_usd` is the API-price equivalent; it isn't billed on a subscription.
- Turn cap: the SDK raises `ResultError` after an `error_max_turns` result. Catch it.
