import json
import re
from html.parser import HTMLParser
from pathlib import Path

from artcrit.site.export import export_site_images
from artcrit.site.model import build_site_data
from artcrit.site.render import render_site

from .conftest import CRIT, outcome


def render(world, out):
    data = build_site_data(world.store, world.tmp)
    return data, render_site(data, export_site_images(data, world.images, out), "<h2>Core</h2>", out)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src") and v:
                self.links.append(v)


def test_writes_expected_files(world, tmp_path):
    d, _ = world.drawing()
    out = tmp_path / "site"
    render(world, out)
    for rel in ("index.html", f"drawings/d{d}.html", "lessons.html", "about.html", "static/site.css",
                "static/overlay.js", ".nojekyll"):
        assert (out / rel).exists(), rel


def test_drawing_page_has_boxes_attribution_outcomes(world, tmp_path):
    d, (s1, s2) = world.drawing(versions=2)
    outcome(world.store, world.store.get_submission(s1).issues[0].id, s2, "fixed")
    world.store.add_revision_metrics(s2, 0.1, 0.08)
    out = tmp_path / "site"
    render(world, out)
    page = (out / f"drawings/d{d}.html").read_text()
    assert page.count('class="box') >= 4  # 2 issues × 2 images, per version
    assert 'href="https://unsplash.com/p"' in page and "Unsplash" in page
    assert "Since v1" in page and 'data-verdict="fixed"' in page and "measured" in page
    assert "20% closer" in page
    assert page.index(">v2<") < page.index(">v1<")  # newest first


def test_all_links_relative(world, tmp_path):
    world.drawing(versions=2)
    out = tmp_path / "site"
    render(world, out)
    for f in out.rglob("*.html"):
        assert not re.search(r'(href|src)="/', f.read_text()), f


def test_every_local_link_resolves(world, tmp_path):
    world.drawing(versions=2)
    out = tmp_path / "site"
    render(world, out)
    for f in out.rglob("*.html"):
        p = Links()
        p.feed(f.read_text())
        for link in p.links:
            if link.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            assert (f.parent / link.split("#")[0]).resolve().exists(), (f, link)


def test_script_in_title_and_license_escaped(world, tmp_path):
    evil = json.loads(CRIT)
    evil["issues"][0]["title"] = "<script>alert(1)</script>"
    world.drawing(url="javascript:alert(2)", license="<img src=x onerror=alert(3)>", crit=json.dumps(evil))
    out = tmp_path / "site"
    render(world, out)
    page = next((out / "drawings").glob("*.html")).read_text()
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page
    assert "<img src=x" not in page and "javascript:" not in page


def test_rerender_removes_stale_pages(world, tmp_path):
    a, _ = world.drawing()
    b, _ = world.drawing()
    out = tmp_path / "site"
    render(world, out)
    assert (out / f"drawings/d{b}.html").exists()
    world.store.add_event("publish_toggle", payload={"publish": False, "drawing_id": b})
    render(world, out)
    assert not (out / f"drawings/d{b}.html").exists() and (out / f"drawings/d{a}.html").exists()
    assert len(list((out / "assets").iterdir())) == 2  # a's drawing + photo only


def test_footer_has_lessons_sha(world, tmp_path):
    world.drawing()
    out = tmp_path / "site"
    data, _ = render(world, out)
    assert f"lessons {data.lessons_sha[:7]}" in (out / "index.html").read_text()


def test_lessons_html_included(world, tmp_path):
    out = tmp_path / "site"
    render(world, out)
    assert "<h2>Core</h2>" in (out / "lessons.html").read_text()
