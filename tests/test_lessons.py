from pathlib import Path

import pytest

from artcrit.lessons import TopicInfo, lessons_sha, list_topics, load_core, load_topic

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def lessons_dir(tmp_path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "core.md").write_text("# Core\n\nAlways measure.\n")
    (tmp_path / "topics" / "hands.md").write_text("# Hands\n\nHand size and finger joints.\n\n## A lesson\n")
    (tmp_path / "topics" / "edges.md").write_text("# Edges\nLost and found edges.\n")
    return tmp_path


def test_load_core(lessons_dir):
    assert "Always measure." in load_core(lessons_dir)


def test_list_topics_sorted_with_descriptions(lessons_dir):
    assert list_topics(lessons_dir) == [
        TopicInfo("edges", "Lost and found edges."),
        TopicInfo("hands", "Hand size and finger joints."),
    ]


def test_load_topic(lessons_dir):
    assert "## A lesson" in load_topic(lessons_dir, "hands")


@pytest.mark.parametrize("name", ["../core", "nope", "topics/hands", "..\\core", ""])
def test_load_topic_rejects_unknown_and_traversal(lessons_dir, name):
    with pytest.raises(KeyError):
        load_topic(lessons_dir, name)


def test_lessons_sha_outside_repo_is_uncommitted(tmp_path):
    assert lessons_sha(tmp_path) == "uncommitted"


def test_repo_core_under_word_cap():
    assert len(load_core(REPO / "lessons").split()) <= 1500


def test_repo_topics_have_descriptions():
    topics = list_topics(REPO / "lessons")
    assert {t.name for t in topics} >= {"faces-proportions", "hands", "values-shading", "figure-proportions", "edges"}
    assert all(t.description for t in topics)
