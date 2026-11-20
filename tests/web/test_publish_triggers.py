from artcrit.config import Settings
from artcrit.site.publish import PublishResult
from artcrit.web.app import create_app
from fastapi.testclient import TestClient

from artcrit.engine.fake import FakeEngine

from .conftest import answer, submit, upload


class SpyPublisher:
    def __init__(self, last=None):
        self.requests = 0
        self._last = last

    def request(self):
        self.requests += 1

    def last(self):
        return self._last


def client_with(tmp_path, script, publisher, state=None):
    lessons = tmp_path / "lessons"
    (lessons / "topics").mkdir(parents=True, exist_ok=True)
    (lessons / "core.md").write_text("# Core\n")
    settings = Settings(data_dir=tmp_path / "data", lessons_dir=lessons, repo_dir=tmp_path, publish_enabled=True)
    if state is not None:
        settings.publish_state.parent.mkdir(parents=True, exist_ok=True)
        settings.publish_state.write_text(state)
    app = create_app(settings, FakeEngine(script), run_in_background=lambda fn: fn(), publisher=publisher)
    return TestClient(app)


def test_done_submission_triggers_publish(tmp_path):
    pub = SpyPublisher()
    client = client_with(tmp_path, [answer()], pub, state='{"lessons_sha": "uncommitted"}')
    submit(client, upload(client).headers["location"])
    assert pub.requests == 1


def test_failed_submission_does_not_publish(tmp_path):
    pub = SpyPublisher()
    client = client_with(tmp_path, [answer("bad"), answer("bad")], pub, state='{"lessons_sha": "uncommitted"}')
    submit(client, upload(client).headers["location"])
    assert pub.requests == 0


def test_startup_publishes_when_lessons_changed(tmp_path):
    pub = SpyPublisher()
    client_with(tmp_path, [], pub, state='{"lessons_sha": "old-sha"}')
    assert pub.requests == 1


def test_startup_quiet_when_lessons_unchanged(tmp_path):
    pub = SpyPublisher()
    client_with(tmp_path, [], pub, state='{"lessons_sha": "uncommitted"}')
    assert pub.requests == 0


def test_footer_shows_last_publish(tmp_path):
    pub = SpyPublisher(PublishResult(True, "abc", False, "no remote 'origin'", "2026-11-20 12:00 UTC"))
    client = client_with(tmp_path, [], pub, state='{"lessons_sha": "uncommitted"}')
    html = client.get("/").text
    assert "2026-11-20 12:00 UTC" in html and "not pushed" in html and "no remote" in html
