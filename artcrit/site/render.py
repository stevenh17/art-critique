"""Render the public site to static HTML with relative links only."""

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from artcrit.site.model import SiteData

HERE = Path(__file__).parent


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(default=True))
    env.filters["pct"] = lambda v: f"{v * 100:.4f}"
    return env


def _clean(out_dir: Path, keep: set[str]) -> None:
    """Remove everything from a previous build except the freshly exported assets."""
    if not out_dir.exists():
        return
    for p in sorted(out_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = p.relative_to(out_dir).as_posix()
        if p.is_file() and rel not in keep:
            p.unlink()
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()


def render_site(data: SiteData, image_map: dict[str, str], lessons_html: str, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    _clean(out_dir, set(image_map.values()))
    env = _env()
    common = {"data": data, "img": image_map}
    pages = {
        "index.html": ("index.html", {"root": ""}),
        "lessons.html": ("lessons.html", {"root": "", "lessons_html": Markup(lessons_html)}),
        "about.html": ("about.html", {"root": ""}),
    }
    for d in data.drawings:
        pages[f"drawings/{d.slug}.html"] = ("drawing.html", {"root": "../", "d": d})
    written = []
    for rel, (template, ctx) in pages.items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(env.get_template(template).render(**common, **ctx))
        written.append(path)
    static = out_dir / "static"
    static.mkdir(parents=True, exist_ok=True)
    for name in ("site.css", "overlay.js"):
        shutil.copyfile(HERE / "static" / name, static / name)
        written.append(static / name)
    (out_dir / ".nojekyll").write_text("")
    return written + [out_dir / ".nojekyll"]
