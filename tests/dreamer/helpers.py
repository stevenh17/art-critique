import subprocess
from pathlib import Path

CORE = """# Core rubric

Checks every critique uses.

## Measure first
- Compare the same measurement in both images.
- Evidence: seed lesson, no sessions yet.
- Added 2026-11-20
"""

HANDS = """# Hands

Size and joints of hands.

## Hand size against the face
- A hand is about a face long.
- Evidence: 4 sessions; fixed on revision in 3. [s1, s2, s3, s4]
- Added 2026-11-20
"""


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def lesson_repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "lessons" / "topics").mkdir(parents=True)
    (r / "lessons" / "core.md").write_text(CORE)
    (r / "lessons" / "topics" / "hands.md").write_text(HANDS)
    (r / "README.md").write_text("x\n")
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r
