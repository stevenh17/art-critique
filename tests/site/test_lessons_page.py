import subprocess

from artcrit.site.lessons_page import lesson_history, lessons_html


def _lessons(root):
    (root / "lessons" / "topics").mkdir(parents=True)
    (root / "lessons" / "core.md").write_text("# Core rubric\n\nMeasure first.\n")
    (root / "lessons" / "topics" / "hands.md").write_text("# Hands\n\nHand checks.\n")
    (root / "lessons" / "topics" / "edges.md").write_text("# Edges\n\nEdge checks.\n")
    return root / "lessons"


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)


def test_renders_core_and_topics_in_order(tmp_path):
    html = lessons_html(tmp_path, _lessons(tmp_path))
    assert html.index("Core rubric") < html.index("Edges") < html.index("Hands")
    assert "<h1" in html and "Measure first." in html


def test_history_from_temp_git_repo(tmp_path):
    lessons = _lessons(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "Seed lessons")
    (lessons / "core.md").write_text("# Core rubric\n\nMeasure twice.\n")
    _git(tmp_path, "commit", "-qam", "Strengthen measuring lesson")
    hist = lesson_history(tmp_path, "lessons/core.md")
    assert [h.subject for h in hist] == ["Strengthen measuring lesson", "Seed lessons"]
    assert "Strengthen measuring lesson" in lessons_html(tmp_path, lessons)


def test_no_repo_gives_empty_history(tmp_path):
    assert lesson_history(tmp_path, "lessons/core.md") == []


def test_raw_html_in_markdown_escaped(tmp_path):
    lessons = _lessons(tmp_path)
    (lessons / "core.md").write_text("# Core\n\n<script>alert(1)</script> and <b>bold</b>\n")
    html = lessons_html(tmp_path, lessons)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_commit_subject_escaped(tmp_path):
    lessons = _lessons(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "<img src=x onerror=alert(1)>")
    assert "<img src=x" not in lessons_html(tmp_path, lessons)
