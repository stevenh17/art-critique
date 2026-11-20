"""Regression tests for the Plan 3 whole-branch review (I-1..I-4)."""

from artcrit.site.lessons_page import lessons_html
from artcrit.site.publish import publish_site

from .test_publish import git
from tests.web.conftest import answer, submit, upload
from tests.web.test_publish_triggers import SpyPublisher, client_with


# I-1: cross-site POSTs are refused
def test_cross_site_post_refused(tmp_path):
    client = client_with(tmp_path, [answer()], SpyPublisher(), state='{"lessons_sha": "uncommitted"}')
    url = submit(client, upload(client).headers["location"]).headers["location"]
    d = client.app.state.store.get_submission(int(url.rsplit("/", 1)[1])).drawing_id
    evil = client.post(f"/drawings/{d}/publish", data={"publish": "on"}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    evil_ref = client.post(f"/drawings/{d}/publish", data={"publish": "on"}, headers={"Referer": "https://evil.example/x"})
    assert evil_ref.status_code == 403
    ok = client.post(f"/drawings/{d}/publish", data={"publish": "off"}, headers={"Origin": "http://testserver"},
                     follow_redirects=False)
    assert ok.status_code == 303


# I-2: the lessons page shows committed lessons on main, not the working tree
def test_lessons_page_reads_main_not_working_tree(tmp_path):
    r = tmp_path / "repo"
    (r / "lessons" / "topics").mkdir(parents=True)
    (r / "lessons" / "core.md").write_text("# Core\n\nMerged text.\n")
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    git(r, "checkout", "-q", "-b", "dreamer-pr")
    (r / "lessons" / "core.md").write_text("# Core\n\nUnreviewed PR text.\n")
    git(r, "commit", "-qam", "dreamer edit")
    (r / "lessons" / "topics" / "draft.md").write_text("# Draft\n\nUncommitted.\n")
    html = lessons_html(r, r / "lessons")
    assert "Merged text." in html and "Unreviewed" not in html and "Uncommitted" not in html


# I-3: no script URLs or remote images from lesson markdown
def test_lesson_markdown_links_sanitized(tmp_path):
    (tmp_path / "lessons" / "topics").mkdir(parents=True)
    (tmp_path / "lessons" / "core.md").write_text(
        "# Core\n\n[bad](javascript:alert(1)) [ok](https://example.org/a) [rel](lessons.html)\n\n![px](https://tracker.example/p.gif)\n")
    html = lessons_html(tmp_path, tmp_path / "lessons")
    assert "javascript:" not in html and "tracker.example" not in html
    assert 'href="https://example.org/a"' in html and 'href="lessons.html"' in html


# I-4: a fresh clone builds on the remote's gh-pages instead of a rejected root commit
def test_fresh_clone_publishes_fast_forward(tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    first = tmp_path / "first"
    git(tmp_path, "clone", "-q", str(bare), str(first))
    (first / "README.md").write_text("x")
    git(first, "add", "-A")
    git(first, "commit", "-qm", "init")
    git(first, "push", "-q", "origin", "HEAD:main")
    site = tmp_path / "site1"
    site.mkdir()
    (site / "index.html").write_text("one")
    assert publish_site(site, first, tmp_path / "s1.json").pushed

    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    site2 = tmp_path / "site2"
    site2.mkdir()
    (site2 / "index.html").write_text("two")
    res = publish_site(site2, clone, tmp_path / "s2.json")
    assert res.pushed, res.message
    assert git(bare, "rev-list", "--count", "gh-pages") == "2"


def test_fresh_clone_without_changes_tracks_remote(tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    first = tmp_path / "first"
    git(tmp_path, "clone", "-q", str(bare), str(first))
    (first / "README.md").write_text("x")
    git(first, "add", "-A")
    git(first, "commit", "-qm", "init")
    git(first, "push", "-q", "origin", "HEAD:main")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("same")
    publish_site(site, first, tmp_path / "s1.json")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    res = publish_site(site, clone, tmp_path / "s2.json")  # identical site
    assert not res.committed and res.pushed, res.message
    assert git(clone, "rev-parse", "gh-pages") == git(bare, "rev-parse", "gh-pages")
