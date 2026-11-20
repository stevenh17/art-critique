from pathlib import Path

import pytest

from artcrit.dreamer.checks import run_checks
from artcrit.dreamer.export import EvidenceRecord, Export, Watermark
from artcrit.dreamer.workspace import LessonWorkspace

from .helpers import CORE, HANDS

REPO = Path(__file__).resolve().parents[2]


def rec(n):
    return EvidenceRecord(f"s{n}", 1, "proportion", "Eyes high", "Lower them.", [], {"thumb_up": 1}, False, [])


EXPORT = Export([rec(10), rec(11), rec(12)], Watermark(12, 0, 0), ["CC BY 4.0 — Jane Doe of the Very Long Name Photography Studio"])


def ws(**files):
    return LessonWorkspace({"lessons/core.md": CORE, "lessons/topics/hands.md": HANDS, **files})


def check(new, base=None, export=EXPORT):
    return [(f.path, f.rule) for f in run_checks(new, base or ws(), export, export.user_texts)]


def lesson(heading="Check eye line", evidence="3 sessions; fixed in 2. [s10, s11, s12]", date="Added 2026-11-21"):
    return f"\n## {heading}\n- Measure the eye line in both images.\n- Evidence: {evidence}\n- {date}\n"


def test_unchanged_passes():
    assert check(ws()) == []


def test_good_new_lesson_passes():
    assert check(ws(**{"lessons/core.md": CORE + lesson()})) == []


@pytest.mark.parametrize("text", ["no heading\n\nx\n", "# T\n\n## Only heading\n- x\n- Added 2026-11-20\n",
                                  "# T\n\nDesc\n\n## H\n- x\n- Evidence: [s10]\n"])
def test_format_failures(text):
    assert ("lessons/topics/hands.md", "format") in check(ws(**{"lessons/topics/hands.md": text}))


def test_empty_core_fails():
    assert ("lessons/core.md", "format") in check(ws(**{"lessons/core.md": ""}))


def test_core_size():
    big = CORE + "\n## Long\n- " + "word " * 1500 + "\n- Evidence: [s10]\n- Added 2026-11-21\n"
    assert ("lessons/core.md", "core_size") in check(ws(**{"lessons/core.md": big}))


def test_fabricated_session_fails():
    bad = CORE + lesson(evidence="3 sessions. [s10, s11, s9999]")
    assert ("lessons/core.md", "evidence_exists") in check(ws(**{"lessons/core.md": bad}))


def test_sessions_already_cited_in_base_are_allowed():
    # hands.md on main already cites s1-s4; keeping them is fine even though they're not in this export
    edited = HANDS.replace("A hand is about a face long.", "A hand is about a face long, wrist to fingertip.")
    assert check(ws(**{"lessons/topics/hands.md": edited})) == []


def test_new_lesson_with_two_sessions_fails():
    bad = CORE + lesson(evidence="2 sessions. [s10, s11]")
    assert ("lessons/core.md", "new_lesson_support") in check(ws(**{"lessons/core.md": bad}))


def test_user_text_overlap_fails():
    bad = CORE + lesson(heading="Credit").replace("Measure the eye line in both images.",
                                                  "cc by 4.0 jane doe of the very long name photography")
    assert ("lessons/core.md", "no_user_text") in check(ws(**{"lessons/core.md": bad}))


@pytest.mark.parametrize("snippet", ["see https://x.org", "www.example.com", "![p](a.png)", "<img src=a>"])
def test_urls_and_images_fail(snippet):
    bad = CORE.replace("Compare the same measurement in both images.", snippet)
    assert ("lessons/core.md", "no_urls_or_images") in check(ws(**{"lessons/core.md": bad}))


def test_edited_seed_lesson_must_cite_a_session():
    edited = CORE.replace("Compare the same measurement", "Always compare the same measurement")
    assert ("lessons/core.md", "seed_edit_needs_evidence") in check(ws(**{"lessons/core.md": edited}))
    cited = edited.replace("Evidence: seed lesson, no sessions yet.", "Evidence: seed lesson; confirmed by [s10].")
    assert check(ws(**{"lessons/core.md": cited})) == []


def test_current_repo_lessons_pass_against_themselves():
    files = {p.relative_to(REPO).as_posix(): p.read_text() for p in (REPO / "lessons").rglob("*.md")}
    assert run_checks(LessonWorkspace(files), LessonWorkspace(files), EXPORT, []) == []
