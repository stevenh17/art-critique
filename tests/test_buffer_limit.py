"""Regression: a real phone-photo drawing (~2.7 MB base64) overflowed the SDK's 1 MB message buffer
when a tool returned it, failing the critique with an opaque CLIJSONDecodeError."""

from artcrit.engine import claude_sdk
from artcrit.imaging.regions import MODEL_MAX_B64

from .web.conftest import make_client, submit, upload  # noqa: F401  (fixture)


def test_sdk_buffer_fits_largest_tool_image(monkeypatch):
    seen = {}

    async def fake_query(prompt, options):
        seen["options"] = options
        return
        yield

    monkeypatch.setattr(claude_sdk, "query", fake_query)
    claude_sdk.ClaudeSDKEngine().run("sys", "p", [], [], 3)
    # outline_compare returns text plus one image; leave room for two full-size images and JSON overhead
    assert seen["options"].max_buffer_size >= 2 * MODEL_MAX_B64 + 1_000_000


def test_unexpected_error_message_is_kept_in_status(make_client):  # noqa: F811
    def boom(tools):
        raise RuntimeError("Buffer size 2743472 exceeds limit 1048576")

    client, _, app = make_client([boom])
    url = submit(client, upload(client).headers["location"]).headers["location"]
    sub = app.state.store.get_submission(int(url.rstrip("/").split("/")[-1]))
    assert sub.status == "failed"
    assert "RuntimeError" in sub.status_detail
    assert "Buffer size 2743472 exceeds limit 1048576" in sub.status_detail
