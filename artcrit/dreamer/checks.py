"""Deterministic gates every dreamer proposal must pass before a branch is created."""

import re
from dataclasses import dataclass

from artcrit.dreamer.export import Export
from artcrit.dreamer.workspace import LessonWorkspace

MAX_CORE_WORDS = 1500
MIN_NEW_LESSON_SESSIONS = 3
OVERLAP_WORDS = 8
_DATE_LINE = re.compile(r"^- (Added|Strengthened|Rewritten|Merged) \d{4}-\d{2}-\d{2}")
_SESSION = re.compile(r"\bs(\d+)\b")
_URLISH = re.compile(r"https?://|www\.|!\[|<img", re.IGNORECASE)


@dataclass
class CheckFailure:
    path: str
    rule: str
    detail: str


def _sections(text: str) -> dict[str, list[str]]:
    """'## heading' -> its lines (until the next '## ')."""
    out, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def _evidence(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("- Evidence:")]


def _sessions(text: str) -> set[str]:
    return {f"s{m}" for m in _SESSION.findall(text)}


def _format(path: str, text: str) -> list[str]:
    lines = text.splitlines()
    problems = []
    if not lines or not lines[0].startswith("# "):
        return ["must start with a '# Title' line"]
    before = []
    for line in lines[1:]:
        if line.startswith("## "):
            break
        before.append(line)
    if not any(line.strip() and not line.startswith("#") for line in before):
        problems.append("needs a one-line description before the first '##' lesson")
    for heading, body in _sections(text).items():
        if len(_evidence(body)) != 1:
            problems.append(f"'{heading}' needs exactly one '- Evidence:' line")
        if not any(_DATE_LINE.match(line) for line in body):
            problems.append(f"'{heading}' needs a dated line like '- Added 2026-11-21'")
    return problems


def _content(lines: list[str]) -> list[str]:
    return [line.rstrip() for line in lines if line.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def run_checks(new: LessonWorkspace, base: LessonWorkspace, export: Export, all_user_texts: list[str]) -> list[CheckFailure]:
    failures: list[CheckFailure] = []
    allowed = {r.session for r in export.records}
    for text in base.files.values():
        allowed |= _sessions(text)
    user_grams = set().union(*(_ngrams(_words(t), OVERLAP_WORDS) for t in all_user_texts)) if all_user_texts else set()

    for path, text in sorted(new.files.items()):
        if not path.endswith(".md"):
            continue
        fail = lambda rule, detail: failures.append(CheckFailure(path, rule, detail))  # noqa: E731
        for problem in _format(path, text):
            fail("format", problem)
        if path.endswith("/core.md") and len(text.split()) > MAX_CORE_WORDS:
            fail("core_size", f"core.md has {len(text.split())} words; limit {MAX_CORE_WORDS}")
        sections = _sections(text)
        base_sections = _sections(base.files.get(path, ""))
        for heading, body in sections.items():
            cited = set().union(*(_sessions(line) for line in _evidence(body))) if _evidence(body) else set()
            unknown = sorted(cited - allowed)
            if unknown:
                fail("evidence_exists", f"'{heading}' cites sessions not in the evidence: {', '.join(unknown)}")
            if heading not in base_sections and len(cited) < MIN_NEW_LESSON_SESSIONS:
                fail("new_lesson_support", f"new lesson '{heading}' cites {len(cited)} sessions; needs {MIN_NEW_LESSON_SESSIONS}")
            old = base_sections.get(heading)
            if old is not None and _content(old) != _content(body) and any("seed lesson" in line for line in _evidence(old)) and not cited:
                fail("seed_edit_needs_evidence", f"seed lesson '{heading}' was changed without citing any session")
        if user_grams and _ngrams(_words(text), OVERLAP_WORDS) & user_grams:
            fail("no_user_text", f"contains {OVERLAP_WORDS}+ words copied from text a user typed")
        if _URLISH.search(text):
            fail("no_urls_or_images", "lessons may not contain links or images")
    return failures
