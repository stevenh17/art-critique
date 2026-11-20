import json

import numpy as np
import pytest

from artcrit.engine.base import AgentResult, UsageLimitError
from artcrit.engine.fake import FakeEngine
from artcrit.judge import judge_issue

OLD = np.full((60, 40, 3), 200, np.uint8)
NEW = np.full((60, 40, 3), 210, np.uint8)
PHOTO = np.full((60, 40, 3), 120, np.uint8)


def reply(text):
    return lambda tools: AgentResult(text, [], "judge-model")


def run(*steps):
    eng = FakeEngine(list(steps))
    return judge_issue("proportion", "Jaw too long", "Shorten the chin by a quarter head.", OLD, NEW, PHOTO, eng), eng


def test_valid_verdict_parsed():
    res, _ = run(reply('Looking closely... {"verdict": "partly", "reason": "Chin moved up but still low."}'))
    assert (res.verdict, res.reason, res.model) == ("partly", "Chin moved up but still low.", "judge-model")


def test_prompt_contains_only_issue_fields():
    _, eng = run(reply(json.dumps({"verdict": "fixed", "reason": "ok"})))
    text = eng.calls[0]["system"] + eng.calls[0]["prompt_text"]
    assert "Jaw too long" in text and "Shorten the chin by a quarter head." in text
    assert "tool_trace" not in text and "lesson" not in text.lower()


def test_three_images_old_new_photo():
    _, eng = run(reply(json.dumps({"verdict": "fixed", "reason": "ok"})))
    assert len(eng.calls[0]["images"]) == 3
    assert "Image 1 is the previous version" in eng.calls[0]["prompt_text"]


def test_no_tools_offered():
    _, eng = run(reply(json.dumps({"verdict": "fixed", "reason": "ok"})))
    assert eng.calls[0]["tools"] == [] and eng.calls[0]["max_turns"] == 2


def test_garbage_twice_gives_cant_tell():
    res, eng = run(reply("no idea"), reply("still nothing"))
    assert (res.verdict, res.reason) == ("cant_tell", "judge output unreadable")
    assert len(eng.calls) == 2


def test_unknown_verdict_value_retried():
    res, eng = run(reply('{"verdict": "great", "reason": "x"}'), reply('{"verdict": "not_fixed", "reason": "y"}'))
    assert res.verdict == "not_fixed" and "great" in eng.calls[1]["prompt_text"]


def test_usage_limit_propagates():
    def boom(tools):
        raise UsageLimitError("five_hour")

    with pytest.raises(UsageLimitError):
        run(boom)
