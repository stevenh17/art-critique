"""Throwaway spike: can the Agent SDK run a bounded, tools-only, image-aware agent
on the user's Claude login (no API key)? See docs/spikes/2026-11-agent-sdk.md."""

import asyncio
import base64
import io
import os

from PIL import Image, ImageDraw
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


def png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def make_image() -> Image.Image:
    img = Image.new("RGB", (320, 240), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((100, 40, 220, 200), outline="black", width=4)  # a "head"
    d.rectangle((20, 20, 60, 60), fill="red")
    return img


IMG = make_image()


@tool("echo_size", "Return the pixel size of the image with the given id.", {"image_id": str})
async def echo_size(args):
    return {"content": [{"type": "text", "text": f"{args['image_id']}: {IMG.width}x{IMG.height}"}]}


@tool("zoom_corner", "Return a zoomed crop of the top-left corner of the image.", {"image_id": str})
async def zoom_corner(args):
    crop = IMG.crop((0, 0, 80, 80)).resize((240, 240))
    return {"content": [{"type": "image", "data": png_b64(crop), "mimeType": "image/png"}]}


async def prompt_stream():
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png_b64(IMG)}},
                {
                    "type": "text",
                    "text": (
                        "This is image 'img1'. First call echo_size on it, then call zoom_corner on it. "
                        "Then reply with one sentence: what shapes you see in the full image and what "
                        "colour the zoomed corner is."
                    ),
                },
            ],
        },
    }


async def main():
    assert not os.environ.get("ANTHROPIC_API_KEY"), "unset ANTHROPIC_API_KEY for this spike"
    server = create_sdk_mcp_server("spike", tools=[echo_size, zoom_corner])
    opts = ClaudeAgentOptions(
        tools=[],  # no built-in tools at all
        mcp_servers={"spike": server},
        strict_mcp_config=True,
        allowed_tools=["mcp__spike__echo_size", "mcp__spike__zoom_corner"],
        permission_mode="dontAsk",
        setting_sources=[],
        system_prompt="You are a test agent. Use only the tools you are given.",
        max_turns=int(os.environ.get("SPIKE_MAX_TURNS", "4")),
    )
    tool_calls, models = [], set()
    async for msg in query(prompt=prompt_stream(), options=opts):
        if isinstance(msg, AssistantMessage):
            models.add(msg.model)
            if msg.error:
                print("ASSISTANT ERROR:", msg.error)
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    tool_calls.append(b.name)
                elif isinstance(b, TextBlock):
                    print("TEXT:", b.text)
        elif isinstance(msg, RateLimitEvent):
            print("RATE LIMIT:", msg.rate_limit_info)
        elif isinstance(msg, ResultMessage):
            print("RESULT:", msg.subtype, "turns", msg.num_turns, "is_error", msg.is_error,
                  "cost", msg.total_cost_usd, "errors", msg.errors)
    print("TOOL CALLS:", tool_calls)
    print("MODELS:", models)


if __name__ == "__main__":
    asyncio.run(main())
