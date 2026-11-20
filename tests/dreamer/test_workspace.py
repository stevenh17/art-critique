import pytest

from artcrit.dreamer.workspace import LessonWorkspace, make_tools, name_to_path

from .helpers import CORE, git, lesson_repo


def tools(ws):
    sink = {}
    return {t.name: t for t in make_tools(ws, sink)}, sink


def test_from_ref_reads_main_not_working_tree(tmp_path):
    r = lesson_repo(tmp_path)
    (r / "lessons" / "core.md").write_text("# Core\n\nuncommitted\n")
    (r / "lessons" / "topics" / "new.md").write_text("# New\n\nuntracked\n")
    ws = LessonWorkspace.from_ref(r, "main")
    assert ws.read("core") == CORE and "topics/new" not in ws.names()


def test_names_and_paths(tmp_path):
    ws = LessonWorkspace.from_ref(lesson_repo(tmp_path), "main")
    assert ws.names() == ["core", "topics/hands"]
    assert name_to_path("core") == "lessons/core.md"
    assert name_to_path("topics/eyes-2") == "lessons/topics/eyes-2.md"


@pytest.mark.parametrize("bad", ["../artcrit/x", "topics/../../x", "/etc/passwd", "topics/X Y", "topics/a.py",
                                 "notes", "topics/", "topics/a/b", ""])
def test_bad_names_rejected(bad):
    with pytest.raises(ValueError):
        name_to_path(bad)


def test_write_tool_returns_error_text_not_exception(tmp_path):
    t, _ = tools(LessonWorkspace.from_ref(lesson_repo(tmp_path), "main"))
    out = t["write_lesson"].handler({"name": "../../artcrit/evil", "content": "x"})
    assert out[0]["type"] == "text" and out[0]["text"].startswith("Error")
    assert t["read_lesson"].handler({"name": "topics/missing"})[0]["text"].startswith("Error")


def test_write_tool_never_touches_disk(tmp_path):
    r = lesson_repo(tmp_path)
    before = {p: p.read_bytes() for p in r.rglob("*") if p.is_file() and ".git" not in p.parts}
    ws = LessonWorkspace.from_ref(r, "main")
    t, _ = tools(ws)
    t["write_lesson"].handler({"name": "core", "content": "# Core\n\nchanged\n"})
    t["write_lesson"].handler({"name": "topics/eyes", "content": "# Eyes\n\nnew\n"})
    after = {p: p.read_bytes() for p in r.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert before == after and git(r, "status", "--porcelain") == ""
    assert ws.read("topics/eyes") == "# Eyes\n\nnew\n"


def test_changed_reports_only_modified_files(tmp_path):
    base = LessonWorkspace.from_ref(lesson_repo(tmp_path), "main")
    ws = base.copy()
    ws.write("core", "# Core\n\nchanged\n")
    ws.write("topics/hands", base.read("topics/hands"))
    assert ws.changed(base) == {"lessons/core.md": "# Core\n\nchanged\n"}


def test_oversized_write_rejected(tmp_path):
    ws = LessonWorkspace.from_ref(lesson_repo(tmp_path), "main")
    with pytest.raises(ValueError):
        ws.write("core", "x" * 20_001)


def test_list_tool_shows_descriptions(tmp_path):
    t, _ = tools(LessonWorkspace.from_ref(lesson_repo(tmp_path), "main"))
    text = t["list_lessons"].handler({})[0]["text"]
    assert "core: Checks every critique uses." in text and "topics/hands: Size and joints of hands." in text


def test_finish_tool_records_summary_and_changes(tmp_path):
    t, sink = tools(LessonWorkspace.from_ref(lesson_repo(tmp_path), "main"))
    changes = [{"lesson": "core", "action": "strengthen", "reason": "fixed 4/5", "sessions": ["s1"]}]
    t["finish"].handler({"summary": "One change.", "changes": changes})
    assert sink["finish"] == {"summary": "One change.", "changes": changes}
