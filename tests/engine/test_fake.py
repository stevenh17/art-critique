import pytest

from artcrit.engine.base import AgentResult, ToolSpec
from artcrit.engine.fake import FakeEngine


def test_fake_runs_script_in_order_and_records_calls():
    tool = ToolSpec("echo", "echo", {"type": "object"}, lambda args: [{"type": "text", "text": args["x"]}])
    eng = FakeEngine([
        lambda tools: AgentResult(tools[0].handler({"x": "hi"})[0]["text"], [], "fake-model"),
        lambda tools: AgentResult("second", [], "fake-model"),
    ])
    assert eng.run("sys", "p", ["img"], [tool], 3).text == "hi"
    assert eng.run("sys", "p2", [], [tool], 3).text == "second"
    assert [c["prompt_text"] for c in eng.calls] == ["p", "p2"]
    assert eng.calls[0]["max_turns"] == 3


def test_fake_raises_when_script_exhausted():
    with pytest.raises(AssertionError):
        FakeEngine([]).run("s", "p", [], [], 1)
