"""Session evidence for the dreamer: structured, text-free records since a watermark."""

import json
from dataclasses import asdict, dataclass

from artcrit.store.sessions import SessionStore


@dataclass(frozen=True)
class Watermark:
    submission: int = 0
    outcome: int = 0
    event: int = 0

    @staticmethod
    def load(text: str | None) -> "Watermark":
        try:
            d = json.loads(text or "")
            return Watermark(int(d["submission"]), int(d["outcome"]), int(d["event"]))
        except (ValueError, TypeError, KeyError):
            return Watermark()

    def dumps(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"


@dataclass
class EvidenceRecord:
    session: str
    issue_number: int
    category: str
    title: str
    instruction: str
    lesson_refs: list[str]
    ratings: dict[str, int]
    intentional: bool
    outcomes: list[dict]


@dataclass
class Export:
    records: list[EvidenceRecord]
    new_watermark: Watermark
    user_texts: list[str]


def export_since(store: SessionStore, wm: Watermark) -> Export:
    records = []
    for r in store.evidence_issue_rows(wm.submission, wm.outcome, wm.event):
        outcomes = [{"verdict": o["final_verdict"], "measured": o["source"].startswith("geometry"),
                     "disagreement": bool(o["disagreement"])} for o in store.issue_outcomes(r["id"])]
        records.append(EvidenceRecord(f"s{r['submission_id']}", r["position"], r["category"], r["title"],
                                      r["instruction"], json.loads(r["lesson_refs"]), store.rating_counts(r["id"]),
                                      store.is_intentional(r["id"]), outcomes))
    sub, out, ev = store.max_ids()
    new = Watermark(max(sub, wm.submission), max(out, wm.outcome), max(ev, wm.event))
    return Export(records, new, store.user_texts())


def has_enough_evidence(export: Export, minimum: int = 3) -> bool:
    useful = [r for r in export.records if r.outcomes or any(r.ratings.values())]
    return len(useful) >= minimum
