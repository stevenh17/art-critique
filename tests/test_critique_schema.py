import json

import pytest

from artcrit.critique_schema import CRITIQUE_JSON_INSTRUCTIONS, CritiqueFormatError, parse_critique


def _issue(category="proportion", cells=("C6", "D6"), title="Jaw too long"):
    return {
        "category": category,
        "title": title,
        "instruction": "The chin ends about a quarter head lower than the photo; shorten from the mouth down.",
        "drawing_cells": list(cells),
        "photo_cells": list(cells),
        "lesson_refs": ["Check eye line before features"],
    }


def _doc(*issues):
    return json.dumps({"issues": list(issues)})


def test_valid_two_issues_parse():
    c = parse_critique(_doc(_issue(), _issue("values", ("B3",), "Shadow too light")))
    assert len(c.issues) == 2
    assert c.issues[0].drawing_box == (0.25, 0.625, 0.5, 0.75)


def test_json_wrapped_in_prose_and_fence():
    text = "Here is my critique.\n```json\n" + _doc(_issue(), _issue("edges", ("A1",))) + "\n```\nDone."
    assert len(parse_critique(text).issues) == 2


def test_last_json_object_wins():
    text = '{"draft": true}\nfinal:\n' + _doc(_issue(), _issue("edges", ("A1",)))
    assert len(parse_critique(text).issues) == 2


@pytest.mark.parametrize(
    "text",
    [
        _doc(_issue()),  # 1 issue
        _doc(*[_issue() for _ in range(4)]),  # 4 issues
        _doc(_issue("composition"), _issue()),  # unknown category
        _doc(_issue(cells=("J9",)), _issue()),  # invalid cell
        _doc(_issue(cells=()), _issue()),  # no cells
        _doc(_issue(title="x" * 81), _issue()),  # title too long
        "no json here",
        '{"issues": "nope"}',
    ],
)
def test_invalid_outputs_raise(text):
    with pytest.raises(CritiqueFormatError):
        parse_critique(text)


def test_sorted_into_instructor_order():
    c = parse_critique(_doc(_issue("edges", ("A1",)), _issue("anatomy", ("B2",)), _issue("proportion")))
    assert [i.category for i in c.issues] == ["proportion", "anatomy", "edges"]


def test_error_message_is_retry_friendly():
    with pytest.raises(CritiqueFormatError) as e:
        parse_critique(_doc(_issue(cells=("J9",)), _issue()))
    assert "J9" in str(e.value)


def test_instructions_name_the_fields_and_limits():
    for word in ("drawing_cells", "photo_cells", "proportion", "anatomy", "values", "edges", "2", "3"):
        assert word in CRITIQUE_JSON_INSTRUCTIONS
